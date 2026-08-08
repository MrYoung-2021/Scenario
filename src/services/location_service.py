from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import hashlib
import os
import time
from typing import Any, Protocol

import httpx

from schemas.location import LocationResult
from utils.config_handler import location_conf


class LocationProviderError(RuntimeError):
    pass


class LocationProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[LocationResult]: ...

    async def close(self) -> None: ...


class NominatimLocationProvider:
    name = "nominatim"

    def __init__(
        self,
        endpoint: str,
        user_agent: str,
        timeout_seconds: float,
        minimum_interval_seconds: float,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        self._clock = clock
        self._sleep = sleep
        self._request_lock = asyncio.Lock()
        self._last_request_started: float | None = None

    async def search(self, query: str, limit: int) -> list[LocationResult]:
        params = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": limit,
        }
        try:
            async with self._request_lock:
                await self._wait_for_rate_limit()
                self._last_request_started = self._clock()
                response = await self._client.get(
                    self.endpoint,
                    params=params,
                    headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                )
                response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocationProviderError("地址服务暂时不可用") from exc

        if not isinstance(payload, list):
            raise LocationProviderError("地址服务返回了无效数据")
        results: list[LocationResult] = []
        for item in payload:
            normalized = self._normalize(item)
            if normalized is not None:
                results.append(normalized)
        return results

    async def _wait_for_rate_limit(self) -> None:
        if self._last_request_started is None:
            return
        remaining = self.minimum_interval_seconds - (
            self._clock() - self._last_request_started
        )
        if remaining > 0:
            await self._sleep(remaining)

    def _normalize(self, item: Any) -> LocationResult | None:
        if not isinstance(item, dict):
            return None
        raw_id = item.get("place_id")
        if raw_id is None and item.get("osm_id") is not None:
            raw_id = f"{item.get('osm_type', 'osm')}:{item['osm_id']}"
        display_name = item.get("display_name")
        try:
            latitude = float(item["lat"])
            longitude = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        if raw_id is None or not display_name:
            return None

        raw_bbox = item.get("boundingbox")
        bbox = None
        if isinstance(raw_bbox, list) and len(raw_bbox) == 4:
            try:
                bbox = tuple(float(value) for value in raw_bbox)
            except (TypeError, ValueError):
                bbox = None
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        try:
            return LocationResult(
                place_id=f"nominatim:{raw_id}",
                display_name=str(display_name),
                country=_first_text(address, "country"),
                admin1=_first_text(address, "state", "province", "region"),
                admin2=_first_text(
                    address,
                    "county",
                    "city",
                    "city_district",
                    "municipality",
                ),
                latitude=latitude,
                longitude=longitude,
                bbox=bbox,
                source=self.name,
            )
        except ValueError:
            return None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class AmapLocationProvider:
    name = "amap"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        user_agent: str,
        timeout_seconds: float,
        minimum_interval_seconds: float,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.user_agent = user_agent
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        self._clock = clock
        self._sleep = sleep
        self._request_lock = asyncio.Lock()
        self._last_request_started: float | None = None

    async def search(self, query: str, limit: int) -> list[LocationResult]:
        try:
            async with self._request_lock:
                await self._wait_for_rate_limit()
                self._last_request_started = self._clock()
                response = await self._client.get(
                    self.endpoint,
                    params={"address": query, "key": self.api_key},
                    headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                )
                response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LocationProviderError("地址服务暂时不可用") from exc
        if not isinstance(payload, dict) or payload.get("status") != "1":
            raise LocationProviderError("地址服务返回了无效数据")

        geocodes = payload.get("geocodes")
        if not isinstance(geocodes, list):
            return []
        results: list[LocationResult] = []
        for item in geocodes[:limit]:
            normalized = self._normalize(item)
            if normalized is not None:
                results.append(normalized)
        return results

    async def _wait_for_rate_limit(self) -> None:
        if self._last_request_started is None:
            return
        remaining = self.minimum_interval_seconds - (
            self._clock() - self._last_request_started
        )
        if remaining > 0:
            await self._sleep(remaining)

    def _normalize(self, item: Any) -> LocationResult | None:
        if not isinstance(item, dict):
            return None
        coordinates = str(item.get("location", "")).split(",")
        if len(coordinates) != 2:
            return None
        display_name = _scalar_text(item.get("formatted_address"))
        if not display_name:
            return None
        try:
            longitude, latitude = (float(value) for value in coordinates)
        except ValueError:
            return None
        identity = hashlib.sha256(
            f"{display_name}|{longitude}|{latitude}".encode("utf-8")
        ).hexdigest()[:20]
        try:
            return LocationResult(
                place_id=f"amap:{identity}",
                display_name=display_name,
                country="中国",
                admin1=_scalar_text(item.get("province")),
                admin2=_scalar_text(item.get("city")) or _scalar_text(item.get("district")),
                latitude=latitude,
                longitude=longitude,
                source=self.name,
            )
        except ValueError:
            return None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class UnavailableLocationProvider:
    def __init__(self, provider_name: str) -> None:
        self.name = provider_name

    async def search(self, query: str, limit: int) -> list[LocationResult]:
        raise LocationProviderError(f"未配置可用的地址 Provider：{self.name}")

    async def close(self) -> None:
        return None


@dataclass
class _CacheEntry:
    expires_at: float
    results: list[LocationResult]


class LocationService:
    def __init__(
        self,
        provider: LocationProvider,
        cache_ttl_seconds: float = 600,
        cache_max_entries: int = 256,
        result_limit: int = 8,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.provider = provider
        self.cache_ttl_seconds = max(0.0, cache_ttl_seconds)
        self.cache_max_entries = max(1, cache_max_entries)
        self.result_limit = min(10, max(1, result_limit))
        self._clock = clock
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()

    async def search(self, query: str) -> list[LocationResult]:
        normalized_query = " ".join(query.split())
        if len(normalized_query) < 2:
            raise ValueError("地址搜索词至少需要 2 个字符")
        cache_key = normalized_query.casefold()
        cached = self._cache.get(cache_key)
        now = self._clock()
        if cached and cached.expires_at > now:
            self._cache.move_to_end(cache_key)
            return list(cached.results)
        if cached:
            self._cache.pop(cache_key, None)

        results = await self.provider.search(normalized_query, self.result_limit)
        self._cache[cache_key] = _CacheEntry(
            expires_at=self._clock() + self.cache_ttl_seconds,
            results=list(results),
        )
        self._cache.move_to_end(cache_key)
        while len(self._cache) > self.cache_max_entries:
            self._cache.popitem(last=False)
        return results

    async def close(self) -> None:
        await self.provider.close()


def create_location_service() -> LocationService:
    provider_name = os.getenv("LOCATION_PROVIDER", location_conf["provider"]).strip().lower()
    if provider_name == "nominatim":
        provider: LocationProvider = NominatimLocationProvider(
            endpoint=os.getenv("LOCATION_ENDPOINT", location_conf["endpoint"]),
            user_agent=os.getenv("LOCATION_USER_AGENT", location_conf["user_agent"]),
            timeout_seconds=_env_float("LOCATION_TIMEOUT_SECONDS", "timeout_seconds"),
            minimum_interval_seconds=_env_float(
                "LOCATION_RATE_INTERVAL_SECONDS",
                "minimum_interval_seconds",
            ),
        )
    elif provider_name == "amap":
        api_key = os.getenv("LOCATION_API_KEY", "").strip()
        if api_key:
            provider = AmapLocationProvider(
                endpoint=os.getenv("LOCATION_ENDPOINT", location_conf["amap_endpoint"]),
                api_key=api_key,
                user_agent=os.getenv("LOCATION_USER_AGENT", location_conf["user_agent"]),
                timeout_seconds=_env_float("LOCATION_TIMEOUT_SECONDS", "timeout_seconds"),
                minimum_interval_seconds=_env_float(
                    "LOCATION_RATE_INTERVAL_SECONDS",
                    "minimum_interval_seconds",
                ),
            )
        else:
            provider = UnavailableLocationProvider("amap（缺少 LOCATION_API_KEY）")
    else:
        provider = UnavailableLocationProvider(provider_name)
    return LocationService(
        provider,
        cache_ttl_seconds=_env_float("LOCATION_CACHE_TTL_SECONDS", "cache_ttl_seconds"),
        cache_max_entries=_env_int("LOCATION_CACHE_MAX_ENTRIES", "cache_max_entries"),
        result_limit=_env_int("LOCATION_RESULT_LIMIT", "result_limit"),
    )


def _first_text(values: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _scalar_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _env_float(env_name: str, config_name: str) -> float:
    return float(os.getenv(env_name, location_conf[config_name]))


def _env_int(env_name: str, config_name: str) -> int:
    return int(os.getenv(env_name, location_conf[config_name]))

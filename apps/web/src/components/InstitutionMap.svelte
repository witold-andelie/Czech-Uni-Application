<script lang="ts">
  import { withBase } from "../lib/base.ts";
  import { operatorListKey, ownershipLabel, recognitionKey } from "../lib/format";
  import { t } from "../lib/i18n";
  import {
    defaultInstitutionQuery,
    filterBaselineInstitutions,
    institutionDisplayName,
    institutionQueryFromSearch,
    operatorListStatus,
    uniqueBaselineCities,
    type InstitutionQuery,
  } from "../lib/institutions";
  import { cityFromBaseline } from "../lib/mergeBrowseCatalog";
  import type { MappedInstitution } from "../lib/loadCoordinates";
  import {
    MAP_SIZE,
    MAX_ZOOM,
    MIN_ZOOM,
    clusterMapPoints,
    coordFilterFromSearch,
    defaultMapView,
    hasCoordinates,
    matchesCoordFilter,
    panMapBy,
    pinScreenTransform,
    projectLonLat,
    searchFromMapQuery,
    shouldClearMapSelection,
    zoomMapAt,
    type CoordFilter,
    type MapCity,
    type MapRegion,
    type MapView,
  } from "../lib/mapProjection";
  import type { UiLocale } from "../lib/types";
  import { onMount, tick } from "svelte";

  let {
    locale,
    schools,
    outlinePath,
    regions = [],
    cities = [],
    neighbors = [],
    rivers = [],
    lakes = [],
  }: {
    locale: UiLocale;
    schools: MappedInstitution[];
    outlinePath: string;
    regions?: MapRegion[];
    cities?: MapCity[];
    neighbors?: string[];
    rivers?: string[];
    lakes?: string[];
  } = $props();

  const CITY_VIEWPORTS: Record<string, { center: [number, number]; zoom: number }> = {
    cz: { center: [15.47, 49.81], zoom: 7 },
    prague: { center: [14.42, 50.08], zoom: 13.5 },
    brno: { center: [16.60, 49.19], zoom: 13.5 },
    ostrava: { center: [18.25, 49.83], zoom: 13.5 },
  };

  let query = $state<InstitutionQuery>(defaultInstitutionQuery());
  let coordFilter = $state<CoordFilter>("all");
  let selectedId = $state<string | null>(null);
  let activeCity = $state<string>("cz");

  // MapLibre state
  let mapMode = $state<"maplibre" | "svg">("maplibre");
  let mapStatus = $state<"initializing" | "loading" | "healthy" | "degraded">("initializing");
  let fallbackReason = $state<"webgl" | "tiles" | "initialization" | "manual" | null>(null);
  let mapContainerEl: HTMLDivElement | undefined;
  let mapInstance: any = null;
  let maplibreglLib: any = null;
  let mapMarkers = new Map<string, {
    marker: any;
    element: HTMLButtonElement;
    memberIds: string[];
    isCluster: boolean;
  }>();
  let tileFailureTimer: number | null = null;
  let tileErrorCount = 0;

  // SVG Map state (fallback & projection)
  let view = $state<MapView>(defaultMapView());
  let dragging = $state(false);
  let dragMoved = $state(false);
  let pointerStart = { x: 0, y: 0 };
  let viewportEl: HTMLDivElement | undefined;

  function hasWebGL(): boolean {
    try {
      const canvas = document.createElement("canvas");
      return Boolean(
        window.WebGLRenderingContext &&
        (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
      );
    } catch {
      return false;
    }
  }

  onMount(() => {
    query = institutionQueryFromSearch(window.location.search);
    coordFilter = coordFilterFromSearch(window.location.search);
    const onPop = () => {
      query = institutionQueryFromSearch(window.location.search);
      coordFilter = coordFilterFromSearch(window.location.search);
    };
    window.addEventListener("popstate", onPop);

    // Check WebGL and load MapLibre GL
    if (!hasWebGL()) {
      switchToSvg("webgl");
    } else {
      import("maplibre-gl").then(async (mod) => {
        // MapLibre GL exports named exports in ESM (Map, Marker, etc.), handle both default and namespace export
        maplibreglLib = mod.default || mod;
        await tick();
        initMapLibre();
      }).catch((err) => {
        console.warn("MapLibre GL load error, falling back to SVG map:", err);
        switchToSvg("initialization");
      });
    }

    return () => {
      window.removeEventListener("popstate", onPop);
      destroyInteractiveMap();
    };
  });

  let visible = $derived(
    filterBaselineInstitutions(
      schools.map((row) => row.institution),
      query,
    )
      .map((item) => schools.find((row) => row.institution.id === item.id))
      .filter((row): row is MappedInstitution => Boolean(row))
      .filter((row) => matchesCoordFilter(row.lat, row.lon, coordFilter)),
  );

  let pins = $derived(
    visible
      .filter((row) => hasCoordinates(row.lat, row.lon))
      .map((row) => ({
        ...row,
        ...projectLonLat(row.lon as number, row.lat as number),
      })),
  );

  let selected = $derived(visible.find((row) => row.institution.id === selectedId) ?? null);
  let labeledCities = $derived(cities.filter((city) => city.rank <= 2 || view.scale >= 1.8));
  let cityOptions = $derived(uniqueBaselineCities(schools.map((row) => row.institution), locale));

  let operatorListedCount = $derived(visible.filter((r) => operatorListStatus(r.institution) === "listed").length);
  let operatorAbsentCount = $derived(visible.filter((r) => operatorListStatus(r.institution) !== "listed").length);

  function syncUrl() {
    const href = `${window.location.pathname}${searchFromMapQuery(query.search, query.ownership, query.cscse, coordFilter, query.city)}`;
    history.replaceState(null, "", href);
  }

  function toggleCity(value: string) {
    query.city = query.city === value ? "all" : value;
    syncUrl();

    if (mapInstance && mapMode === "maplibre") {
      const cityKey = query.city.toLowerCase();
      if (CITY_VIEWPORTS[cityKey]) {
        activeCity = cityKey;
        mapInstance.flyTo({
          center: CITY_VIEWPORTS[cityKey].center,
          zoom: CITY_VIEWPORTS[cityKey].zoom,
          essential: true,
          duration: 900,
        });
      } else if (query.city === "all") {
        activeCity = "cz";
        mapInstance.flyTo({
          center: CITY_VIEWPORTS.cz.center,
          zoom: CITY_VIEWPORTS.cz.zoom,
          essential: true,
          duration: 900,
        });
      } else {
        const citySchools = schools.filter(
          (s) => cityFromBaseline(s.institution).en === query.city && hasCoordinates(s.lat, s.lon),
        );
        if (citySchools.length > 0) {
          const avgLon = citySchools.reduce((sum, s) => sum + (s.lon ?? 0), 0) / citySchools.length;
          const avgLat = citySchools.reduce((sum, s) => sum + (s.lat ?? 0), 0) / citySchools.length;
          mapInstance.flyTo({
            center: [avgLon, avgLat],
            zoom: 13,
            essential: true,
            duration: 900,
          });
        }
      }
    }
  }

  function toggleOwnership(value: InstitutionQuery["ownership"]) {
    query.ownership = query.ownership === value ? "all" : value;
    syncUrl();
  }

  function toggleCscse(value: InstitutionQuery["cscse"]) {
    query.cscse = query.cscse === value ? "all" : value;
    syncUrl();
  }

  function toggleCoords(value: CoordFilter) {
    coordFilter = coordFilter === value ? "all" : value;
    syncUrl();
  }

  function clearFilters() {
    query = defaultInstitutionQuery();
    coordFilter = "all";
    selectedId = null;
    history.replaceState(null, "", window.location.pathname);
  }

  function select(id: string) {
    selectedId = selectedId === id ? null : id;
    if (!selectedId) return;

    // If MapLibre is active, smoothly fly to institution
    if (mapInstance && mapMode === "maplibre") {
      const found = schools.find((row) => row.institution.id === id);
      if (found && hasCoordinates(found.lat, found.lon)) {
        mapInstance.flyTo({
          center: [found.lon, found.lat],
          zoom: Math.max(mapInstance.getZoom(), 14),
          essential: true,
          duration: 900,
        });
      }
    }

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(`map-school-${id}`)?.scrollIntoView({
      block: "center",
      behavior: reduce ? "auto" : "smooth",
    });
  }

  function jumpCity(cityKey: string) {
    activeCity = cityKey;
    const vp = CITY_VIEWPORTS[cityKey];
    if (!vp) return;
    if (mapInstance && mapMode === "maplibre") {
      mapInstance.flyTo({
        center: vp.center,
        zoom: vp.zoom,
        essential: true,
        duration: 1100,
      });
    }
  }

  function destroyInteractiveMap() {
    if (tileFailureTimer !== null) {
      window.clearTimeout(tileFailureTimer);
      tileFailureTimer = null;
    }
    for (const entry of mapMarkers.values()) entry.marker.remove();
    mapMarkers.clear();
    const current = mapInstance;
    mapInstance = null;
    if (current) current.remove();
  }

  function switchToSvg(reason: "webgl" | "tiles" | "initialization" | "manual") {
    fallbackReason = reason;
    mapMode = "svg";
    mapStatus = "degraded";
    destroyInteractiveMap();
  }

  async function retryInteractiveMap() {
    if (!hasWebGL()) {
      switchToSvg("webgl");
      return;
    }
    fallbackReason = null;
    tileErrorCount = 0;
    mapMode = "maplibre";
    mapStatus = "initializing";
    await tick();
    try {
      if (!maplibreglLib) {
        const mod = await import("maplibre-gl");
        maplibreglLib = mod.default || mod;
      }
      initMapLibre();
    } catch (error) {
      console.warn("MapLibre GL retry failed, using SVG map:", error);
      switchToSvg("initialization");
    }
  }

  function initMapLibre() {
    if (!mapContainerEl || !maplibreglLib) return;

    try {
      mapInstance = new maplibreglLib.Map({
        container: mapContainerEl,
        style: {
          version: 8,
          sources: {
            "osm-tiles": {
              type: "raster",
              tiles: [
                "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
              ],
              tileSize: 256,
              attribution: "© OpenStreetMap contributors",
            },
          },
          layers: [
            {
              id: "osm-layer",
              type: "raster",
              source: "osm-tiles",
              minzoom: 0,
              maxzoom: 19,
            },
          ],
        },
        center: CITY_VIEWPORTS.cz.center,
        zoom: CITY_VIEWPORTS.cz.zoom,
        scrollZoom: true,
        cooperativeGestures: false,
        locale: {
          "AttributionControl.ToggleAttribution": t(locale, "map.attributionToggle"),
          "FullscreenControl.Enter": t(locale, "map.fullscreenEnter"),
          "FullscreenControl.Exit": t(locale, "map.fullscreenExit"),
          "Map.Title": t(locale, "map.canvas"),
          "Marker.Title": t(locale, "map.marker"),
          "NavigationControl.ResetBearing": t(locale, "map.resetNorth"),
          "NavigationControl.ZoomIn": t(locale, "map.zoomIn"),
          "NavigationControl.ZoomOut": t(locale, "map.zoomOut"),
          "CooperativeGesturesHandler.WindowsHelpText": t(locale, "map.gestureWindows"),
          "CooperativeGesturesHandler.MacHelpText": t(locale, "map.gestureMac"),
          "CooperativeGesturesHandler.MobileHelpText": t(locale, "map.gestureMobile"),
        },
      });

      mapInstance.addControl(new maplibreglLib.NavigationControl(), "top-right");
      mapInstance.addControl(new maplibreglLib.FullscreenControl(), "top-right");
      mapInstance.addControl(new maplibreglLib.ScaleControl({ unit: "metric" }), "bottom-left");

      mapStatus = "loading";
      mapInstance.on("load", () => {
        mapInstance.resize();
        syncMapLibreMarkers(visible);
        syncMarkerSelection(selectedId);
      });
      mapInstance.on("idle", () => {
        if (mapMode === "maplibre" && mapInstance?.areTilesLoaded()) {
          mapStatus = "healthy";
        }
      });
      mapInstance.on("zoomend", () => {
        syncMapLibreMarkers(visible);
        syncMarkerSelection(selectedId);
      });
      mapInstance.on("click", () => {
        selectedId = null;
      });
      mapInstance.on("sourcedata", (event: any) => {
        if (event.sourceId === "osm-tiles" && event.isSourceLoaded && mapInstance?.areTilesLoaded()) {
          tileErrorCount = 0;
          mapStatus = "healthy";
          if (tileFailureTimer !== null) {
            window.clearTimeout(tileFailureTimer);
            tileFailureTimer = null;
          }
        }
      });
      mapInstance.on("error", (event: any) => {
        if (mapMode !== "maplibre") return;
        const message = String(event?.error?.message || event?.error || "");
        const tileFailure = event?.sourceId === "osm-tiles" || /tile|openstreetmap|raster/i.test(message);
        if (!tileFailure) return;
        tileErrorCount += 1;
        if (tileErrorCount >= 3) switchToSvg("tiles");
      });
      tileFailureTimer = window.setTimeout(() => {
        if (mapInstance && !mapInstance.areTilesLoaded()) switchToSvg("tiles");
      }, 12000);
    } catch (e) {
      console.warn("MapLibre GL initialization failed, switching to SVG:", e);
      switchToSvg("initialization");
    }
  }

  function markerOffset(row: MappedInstitution, rows: MappedInstitution[]): [number, number] {
    const colocated = rows
      .filter((item) => item.lat === row.lat && item.lon === row.lon)
      .sort((a, b) => a.institution.id.localeCompare(b.institution.id));
    if (colocated.length < 2) return [0, 0];
    const index = colocated.findIndex((item) => item.institution.id === row.institution.id);
    const angle = (index / colocated.length) * Math.PI * 2 - Math.PI / 2;
    const radius = Math.min(44, 26 + colocated.length * 2);
    return [Math.cos(angle) * radius, Math.sin(angle) * radius];
  }

  function syncMapLibreMarkers(rows: MappedInstitution[]) {
    if (!mapInstance || !maplibreglLib) return;

    const mappedVisible = rows.filter((row) => hasCoordinates(row.lat, row.lon));
    const groups = clusterMapPoints(
      mappedVisible.map((row) => ({
        id: row.institution.id,
        lat: row.lat as number,
        lon: row.lon as number,
        value: row,
      })),
      mapInstance.getZoom(),
    );
    const nextIds = new Set(groups.map((group) => group.id));
    for (const [id, entry] of mapMarkers) {
      if (!nextIds.has(id)) {
        entry.marker.remove();
        mapMarkers.delete(id);
      }
    }

    groups.forEach((group) => {
      const rowsInGroup = group.points.map((point) => point.value);
      const isCluster = rowsInGroup.length > 1;
      const row = rowsInGroup[0];
      const isOperatorListed = operatorListStatus(row.institution) === "listed";
      const existing = mapMarkers.get(group.id);
      const label = isCluster
        ? t(locale, "map.clusterLabel", { n: rowsInGroup.length })
        : `${institutionDisplayName(row.institution, locale)} (${t(locale, operatorListKey(operatorListStatus(row.institution)))})`;
      if (existing) {
        existing.element.title = label;
        existing.element.setAttribute("aria-label", label);
        existing.marker
          .setLngLat([group.lon, group.lat])
          .setOffset(isCluster ? [0, 0] : markerOffset(row, mappedVisible));
        return;
      }

      const el = document.createElement("button");
      el.type = "button";
      el.className = isCluster
        ? "maplibre-cluster"
        : `maplibre-pin ${isOperatorListed ? "cscse-operator-listed" : "cscse-operator-absent"}`;
      el.title = label;
      el.setAttribute("aria-label", label);
      el.dataset.clusterSize = String(rowsInGroup.length);
      if (!isCluster) {
        el.setAttribute("aria-pressed", "false");
      }

      const inner = document.createElement("span");
      inner.className = isCluster ? "maplibre-cluster-inner" : "maplibre-pin-inner";
      inner.innerText = isCluster
        ? String(rowsInGroup.length)
        : isOperatorListed
          ? "✓"
          : (institutionDisplayName(row.institution, locale).slice(0, 1) || "○");
      el.appendChild(inner);

      const marker = new maplibreglLib.Marker({
        element: el,
        offset: isCluster ? [0, 0] : markerOffset(row, mappedVisible),
      })
        .setLngLat([group.lon, group.lat])
        .addTo(mapInstance);

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        if (isCluster) {
          expandCluster(group.lon, group.lat, rowsInGroup.map((item) => item.institution.id));
        } else {
          select(row.institution.id);
        }
      });

      mapMarkers.set(group.id, {
        marker,
        element: el,
        memberIds: rowsInGroup.map((item) => item.institution.id),
        isCluster,
      });
    });
  }

  function expandCluster(lon: number, lat: number, memberIds: string[]) {
    if (!mapInstance) return;
    const focusId = memberIds[0];
    mapInstance.once("moveend", () => {
      syncMapLibreMarkers(visible);
      const next = [...mapMarkers.values()].find((entry) => entry.memberIds.includes(focusId));
      next?.element.focus();
    });
    mapInstance.flyTo({
      center: [lon, lat],
      zoom: Math.min(14, Math.max(mapInstance.getZoom() + 2.5, 10)),
      essential: true,
      duration: 700,
    });
  }

  function syncMarkerSelection(id: string | null) {
    for (const entry of mapMarkers.values()) {
      const selected = id !== null && entry.memberIds.includes(id);
      entry.element.classList.toggle("selected", selected);
      if (!entry.isCluster) entry.element.setAttribute("aria-pressed", String(selected));
    }
  }

  // Reconcile marker nodes in place so keyboard focus survives selection and
  // filter changes whenever the focused institution remains visible.
  $effect(() => {
    const _v = visible;
    const _s = selectedId;
    if (mapMode === "maplibre" && mapInstance) {
      syncMapLibreMarkers(_v);
      syncMarkerSelection(_s);
    }
  });

  // SVG Fallback interactions
  function clientToViewBox(event: { clientX: number; clientY: number }): { x: number; y: number } {
    const rect = viewportEl?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) {
      return { x: MAP_SIZE.width / 2, y: MAP_SIZE.height / 2 };
    }
    return {
      x: ((event.clientX - rect.left) / rect.width) * MAP_SIZE.width,
      y: ((event.clientY - rect.top) / rect.height) * MAP_SIZE.height,
    };
  }

  function zoomBy(factor: number, origin?: { x: number; y: number }) {
    const point = origin ?? { x: MAP_SIZE.width / 2, y: MAP_SIZE.height / 2 };
    view = zoomMapAt(view, factor, point.x, point.y);
  }

  function resetView() {
    view = defaultMapView();
  }

  function onWheel(event: WheelEvent) {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.18 : 1 / 1.18;
    zoomBy(factor, clientToViewBox(event));
  }

  function onPointerDown(event: PointerEvent) {
    if (event.button !== 0) return;
    dragging = true;
    dragMoved = false;
    pointerStart = { x: event.clientX, y: event.clientY };
    viewportEl?.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent) {
    if (!dragging) return;
    const dist = Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y);
    if (dist > 5) dragMoved = true;
    const rect = viewportEl?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const dx = (event.movementX / rect.width) * MAP_SIZE.width;
    const dy = (event.movementY / rect.height) * MAP_SIZE.height;
    view = panMapBy(view, dx, dy);
  }

  function onPointerUp(event: PointerEvent) {
    const moved = dragMoved;
    dragging = false;
    dragMoved = false;
    if (shouldClearMapSelection(moved, event.target)) selectedId = null;
  }

  function onMapKey(event: KeyboardEvent) {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomBy(1.25);
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      zoomBy(1 / 1.25);
    } else if (event.key === "0") {
      event.preventDefault();
      resetView();
    } else if (event.key === "Escape") {
      event.preventDefault();
      selectedId = null;
    }
  }
</script>

<div class="layout-map">
  <section class="map-stage-wrap" aria-label={t(locale, "map.canvas")}>
    <!-- Quick City Jump Toolbar -->
    <div class="map-city-jumps" role="navigation" aria-label={t(locale, "map.title")}>
      <button type="button" class="btn chip city-chip" class:active={activeCity === "cz"} onclick={() => jumpCity("cz")}>
        {t(locale, "map.city.cz")}
      </button>
      <button type="button" class="btn chip city-chip" class:active={activeCity === "prague"} onclick={() => jumpCity("prague")}>
        {t(locale, "map.city.prague")}
      </button>
      <button type="button" class="btn chip city-chip" class:active={activeCity === "brno"} onclick={() => jumpCity("brno")}>
        {t(locale, "map.city.brno")}
      </button>
      <button type="button" class="btn chip city-chip" class:active={activeCity === "ostrava"} onclick={() => jumpCity("ostrava")}>
        {t(locale, "map.city.ostrava")}
      </button>
    </div>

    <!-- Map Viewport Container -->
    <div
      class="map-viewport-container"
      data-map-status={mapStatus}
      data-map-provider="osm-raster"
    >
      {#if mapStatus !== "degraded"}
        <div class="maplibre-viewport" class:revealed={mapStatus === "healthy"} bind:this={mapContainerEl}></div>
        {#if mapStatus === "healthy"}
          <div class="maplibre-legend card" role="note">
            <div class="legend-header">{t(locale, "map.legend.cscseTitle")}</div>
            <div class="legend-item">
              <span class="legend-dot listed">✓</span>
              <span>{t(locale, "map.legend.cscseOperatorListed", { n: operatorListedCount })}</span>
            </div>
            <div class="legend-item">
              <span class="legend-dot not-found">○</span>
              <span>{t(locale, "map.legend.cscseOperatorAbsent", { n: operatorAbsentCount })}</span>
            </div>
            <button class="btn btn-sm" type="button" onclick={() => switchToSvg("manual")}>
              {t(locale, "map.useOverview")}
            </button>
          </div>
        {:else}
          <p class="map-loading-banner">{t(locale, "map.loadingStatus")}</p>
        {/if}
      {/if}
      {#if fallbackReason}
          <div class="webgl-fallback-banner card" role="status">
            <p>
              ⚠️ {t(locale,
                fallbackReason === "webgl"
                  ? "map.webglFallback"
                  : fallbackReason === "tiles"
                    ? "map.tilesFallback"
                    : fallbackReason === "manual"
                      ? "map.overviewMode"
                      : "map.initializationFallback")}
            </p>
            <button class="btn btn-sm" type="button" onclick={retryInteractiveMap}>
              {t(locale, "map.tryInteractive")}
            </button>
          </div>
      {/if}

        {#if mapStatus !== "healthy"}
        <div class="map-legend" role="group" aria-label={t(locale, "map.legend")}>
          <span class="legend-item">
            <span class="pin-mark listed" aria-hidden="true"></span>
            {t(locale, "map.legend.operatorListed")}
          </span>
          <span class="legend-item">
            <span class="pin-mark not-found" aria-hidden="true"></span>
            {t(locale, "map.legend.operatorAbsent")}
          </span>
          <span class="legend-item">{t(locale, "map.legend.cities")}</span>
        </div>
        {/if}

        <div
          class="map-viewport svg-basemap"
          class:dragging
          class:interactive={mapStatus !== "healthy"}
          bind:this={viewportEl}
          tabindex="0"
          role="application"
          aria-hidden={mapStatus === "healthy"}
          aria-label={t(locale, "map.canvas")}
          onwheel={onWheel}
          onpointerdown={onPointerDown}
          onpointermove={onPointerMove}
          onpointerup={onPointerUp}
          onpointercancel={onPointerUp}
          onkeydown={onMapKey}
        >
          <div
            class="map-world"
            style={`--map-scale: ${view.scale}; transform: translate(${(view.tx / MAP_SIZE.width) * 100}%, ${(view.ty / MAP_SIZE.height) * 100}%) scale(${view.scale});`}
          >
            <svg
              viewBox={`0 0 ${MAP_SIZE.width} ${MAP_SIZE.height}`}
              preserveAspectRatio="none"
              role="presentation"
              aria-hidden="true"
            >
              {#each neighbors as path, index (index)}
                <path class="map-neighbor" d={path}></path>
              {/each}
              {#if regions.length > 0}
                {#each regions as region (region.id)}
                  <path class={`czechia-region ${region.id}`} d={region.path}></path>
                {/each}
              {:else if outlinePath}
                <path class="czechia-land" d={outlinePath}></path>
              {/if}
              {#each lakes as path, index (`lake-${index}`)}
                <path class="map-lake" d={path}></path>
              {/each}
              {#each rivers as path, index (`river-${index}`)}
                <path class="map-river" d={path}></path>
              {/each}
            </svg>
            {#each labeledCities as city (city.id)}
              {@const point = projectLonLat(city.lon, city.lat)}
              <span
                class="map-city"
                class:major={city.rank === 1}
                style={`left: ${(point.x / MAP_SIZE.width) * 100}%; top: ${(point.y / MAP_SIZE.height) * 100}%; transform: translate(-50%, -130%) scale(${1 / view.scale});`}
              >
                {city.names[locale]}
              </span>
            {/each}
            {#each pins as pin (pin.institution.id)}
              <button
                type="button"
                class="map-pin"
                class:listed={operatorListStatus(pin.institution) === "listed"}
                class:not-found={operatorListStatus(pin.institution) !== "listed"}
                class:selected={selectedId === pin.institution.id}
                style={`left: ${(point => (point.x / MAP_SIZE.width) * 100)(pin)}%; top: ${(point => (point.y / MAP_SIZE.height) * 100)(pin)}%; transform: ${pinScreenTransform(view.scale)};`}
                aria-pressed={selectedId === pin.institution.id}
                aria-label={`${institutionDisplayName(pin.institution, locale)} · ${t(locale, operatorListKey(operatorListStatus(pin.institution)))}`}
                onclick={() => select(pin.institution.id)}
                onpointerdown={(event) => event.stopPropagation()}
              >
                <span class="pin-mark" class:listed={operatorListStatus(pin.institution) === "listed"} class:not-found={operatorListStatus(pin.institution) !== "listed"} aria-hidden="true"></span>
              </button>
            {/each}
          </div>
          {#if mapStatus !== "healthy"}
          <div class="map-zoom" role="group" aria-label={t(locale, "map.zoom")} onpointerdown={(event) => event.stopPropagation()}>
            <button class="btn" type="button" onclick={() => zoomBy(1.25)} disabled={view.scale >= MAX_ZOOM}>{t(locale, "map.zoomIn")}</button>
            <button class="btn" type="button" onclick={() => zoomBy(1 / 1.25)} disabled={view.scale <= MIN_ZOOM}>{t(locale, "map.zoomOut")}</button>
            <button class="btn" type="button" onclick={resetView} disabled={view.scale === 1 && view.tx === 0 && view.ty === 0}>{t(locale, "map.zoomReset")}</button>
          </div>
          {/if}
        </div>

    </div>

    <!-- A79: the selected-school card lives in its own region. On constrained
           viewports it stays in normal document flow below the map; on large
           screens it overlays the map's lower-left corner. -->
    {#if selected}
        <div class="map-selected-region">
          <div class="map-selected-card card">
            <button type="button" class="card-close-btn" onclick={() => selectedId = null} aria-label={t(locale, "map.closeCard")}>✕</button>
            <div class="tag-row">
              <span class={`tag ${selected.institution.ownership}`}>
                {ownershipLabel(selected.institution.ownership, locale)}
              </span>
              <span class={`tag cscse-${selected.institution.cscseLookupStatus}`}>
                {t(locale, recognitionKey(selected.institution.cscseLookupStatus))}
              </span>
              <span class="tag city-tag">{selected.institution.region}</span>
            </div>
            <h3>
              <a href={withBase(`/${locale}/institutions/${selected.institution.id}`)}>
                {institutionDisplayName(selected.institution, locale)}
              </a>
            </h3>
            <p class="muted selected-card-official" style="font-size: 0.85rem; margin-bottom: 0.5rem;">
              {selected.institution.officialName}
            </p>
            <p class={`cscse-callout-note ${operatorListStatus(selected.institution) === "listed" ? "listed" : "not-found"}`}>
              {t(locale, "institutions.cscseOperatorNote")}
            </p>
            <div class="card-actions">
              <a class="btn primary btn-sm" href={withBase(`/${locale}/institutions/${selected.institution.id}`)}>
                {t(locale, "institutions.open")} ↗
              </a>
              {#if selected.institution.officialUrl}
                <a class="btn btn-sm" href={selected.institution.officialUrl} target="_blank" rel="noopener noreferrer">
                  {t(locale, "institutions.website")} ↗
                </a>
            {/if}
            </div>
          </div>
        </div>
    {/if}
  </section>

  <section class="map-list-wrap" aria-label={t(locale, "map.list")}>
    <div class="directory-toolbar">
      <div class="chip-group">
        <label for="map-search" class="visually-hidden">{t(locale, "institutions.search")}</label>
        <input
          id="map-search"
          type="text"
          placeholder={t(locale, "institutions.search.placeholder")}
          value={query.search}
          oninput={(event) => {
            query.search = (event.target as HTMLInputElement).value;
            syncUrl();
          }}
        />
        <div class="chip-row chip-row-scroll" role="group" aria-label={t(locale, "filter.city")}>
          <button type="button" class="chip" aria-pressed={query.city === "all"} onclick={() => toggleCity("all")}>
            {t(locale, "filter.all")}
          </button>
          {#each cityOptions as city (city.value)}
            <button type="button" class="chip" aria-pressed={query.city === city.value} onclick={() => toggleCity(city.value)}>
              {city.label}
            </button>
          {/each}
        </div>
      </div>
      <div class="chip-row" role="group" aria-label={t(locale, "filter.ownership")}>
        <button type="button" class="chip" aria-pressed={query.ownership === "public"} onclick={() => toggleOwnership("public")}>
          {t(locale, "institution.public")}
        </button>
        <button type="button" class="chip" aria-pressed={query.ownership === "private"} onclick={() => toggleOwnership("private")}>
          {t(locale, "institution.private")}
        </button>
      </div>
      <div class="chip-row" role="group" aria-label={t(locale, "filter.recognition")}>
        <button type="button" class="chip" aria-pressed={query.cscse === "operator_listed"} onclick={() => toggleCscse("operator_listed")}>
          {t(locale, "recognition.operatorListed")}
        </button>
        <button type="button" class="chip" aria-pressed={query.cscse === "listed"} onclick={() => toggleCscse("listed")}>
          {t(locale, "recognition.listed")}
        </button>
      </div>
      <div class="chip-row" role="group" aria-label={t(locale, "map.legend")}>
        <button type="button" class="chip" aria-pressed={coordFilter === "mapped"} onclick={() => toggleCoords("mapped")}>
          {t(locale, "map.filter.mapped")}
        </button>
        <button type="button" class="chip" aria-pressed={coordFilter === "missing"} onclick={() => toggleCoords("missing")}>
          {t(locale, "map.filter.missing")}
        </button>
      </div>
      <p class="muted">{t(locale, "filter.count", { n: visible.length })} · {t(locale, "map.pins", { n: pins.length })}</p>
      {#if query.city !== "all" || query.ownership !== "all" || query.cscse !== "all" || coordFilter !== "all"}
        <button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button>
      {/if}
    </div>

    {#if visible.length === 0}
      <div class="empty card">
        <h2>{t(locale, "empty.title")}</h2>
        <p>{t(locale, "empty.help")}</p>
        <p><button class="btn" type="button" onclick={clearFilters}>{t(locale, "filter.clear")}</button></p>
      </div>
    {:else}
      <div class="map-school-list" role="list">
        {#each visible as item (item.institution.id)}
          {@const mapped = hasCoordinates(item.lat, item.lon)}
          {@const isOperatorListed = operatorListStatus(item.institution) === "listed"}
          {@const isSelected = selectedId === item.institution.id}
          <div
            class="map-school-row"
            class:selected={isSelected}
            id={`map-school-${item.institution.id}`}
            role="listitem"
          >
            <button
              type="button"
              class="map-school-pick"
              onclick={() => (mapped ? select(item.institution.id) : undefined)}
              disabled={!mapped}
              aria-pressed={isSelected}
            >
              <div class="school-pick-title">
                <span class={`school-dot ${isOperatorListed ? "listed" : "not-found"}`}></span>
                <span class="map-school-name">{institutionDisplayName(item.institution, locale)}</span>
                {#if isSelected}
                  <span class="selected-pill">✓ {t(locale, "map.selectedTag")}</span>
                {/if}
              </div>
              <span class="muted">
                {ownershipLabel(item.institution.ownership, locale)}
                · {t(locale, operatorListKey(operatorListStatus(item.institution)))}
                {#if !mapped}
                  · {t(locale, "map.noCoordinates")}
                {/if}
              </span>
            </button>
            <a class="map-school-open" href={withBase(`/${locale}/institutions/${item.institution.id}`)}>{t(locale, "institutions.open")}</a>
          </div>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  .map-city-jumps {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    align-items: center;
    padding-bottom: 6px;
  }

  .city-chip {
    font-size: 0.8rem;
    padding: 3px 10px;
    border-radius: 6px;
    min-height: 28px;
    background: #f1f5f9;
    border: 1px solid var(--color-border);
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .city-chip:hover {
    background: #e2e8f0;
  }

  .city-chip.active {
    background: #0f172a;
    color: #fff;
    border-color: #0f172a;
  }

  .map-viewport-container {
    position: relative;
    width: 100%;
    /* A79/A88: one effective height rule. The clamp is a real floor — a later
       min-height: 0 here previously won the cascade and collapsed the
       MapLibre renderer to zero height on phones, where the absolutely
       positioned canvas gives the auto grid track no intrinsic height. The
       stage row stretch still sizes the map beside the school list on
       desktop. */
    min-height: clamp(420px, calc(100vh - 240px), 850px);
    height: 100%;
    border-radius: var(--radius-control);
    overflow: hidden;
    background: #e2e8f0;
  }

  .maplibre-viewport {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 1;
    opacity: 0;
    pointer-events: none;
  }

  .maplibre-viewport.revealed {
    opacity: 1;
    pointer-events: auto;
  }

  .svg-basemap {
    position: absolute;
    inset: 0;
    min-height: 0;
    z-index: 0;
    pointer-events: none;
  }

  .svg-basemap.interactive {
    z-index: 2;
    pointer-events: auto;
  }

  .map-loading-banner {
    position: absolute;
    top: 12px;
    left: 12px;
    z-index: 3;
    margin: 0;
    padding: 0.4rem 0.7rem;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.92);
    font-size: 0.8rem;
    pointer-events: none;
  }

  /* Floating Legend */
  .maplibre-legend {
    position: absolute;
    top: 12px;
    left: 12px;
    z-index: 10;
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(226, 232, 240, 0.9);
    border-radius: 8px;
    padding: 0.55rem 0.8rem;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12);
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.775rem;
    pointer-events: auto;
  }

  .legend-header {
    font-weight: 700;
    color: #1e293b;
    font-size: 0.75rem;
    letter-spacing: 0.02em;
    margin-bottom: 0.1rem;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    color: #334155;
  }

  .legend-dot {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 800;
    color: #fff;
    flex-shrink: 0;
  }

  .legend-dot.listed {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    box-shadow: 0 1px 3px rgba(5, 150, 105, 0.35);
  }

  .legend-dot.not-found {
    background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%);
    box-shadow: 0 1px 3px rgba(100, 116, 139, 0.3);
  }

  .webgl-fallback-banner {
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 12;
    max-width: min(520px, calc(100% - 96px));
    padding: 0.75rem 1rem;
    background: #fffbeb;
    border-left: 4px solid #f59e0b;
    font-size: 0.85rem;
  }

  .webgl-fallback-banner p {
    margin: 0 0 0.5rem;
  }

  /* A79: selected-card region. Base (narrow or short viewports): normal
     document flow below the map, so name/actions/close stay reachable. */
  .map-selected-region {
    margin-top: var(--space-12);
    min-width: 0;
  }

  .map-selected-card {
    position: relative;
    max-width: min(420px, 100%);
    z-index: 20;
    background: rgba(255, 255, 255, 0.96);
    backdrop-filter: blur(10px);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-card);
    padding: 1rem;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.15);
  }

  .card-close-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    border: none;
    background: transparent;
    cursor: pointer;
    font-size: 1rem;
    color: var(--color-muted);
    padding: 4px 8px;
  }

  .card-close-btn:hover {
    color: #0f172a;
  }

  .cscse-callout-note {
    font-size: 0.775rem;
    line-height: 1.4;
    padding: 0.4rem 0.6rem;
    border-radius: 4px;
    margin-bottom: 0.6rem;
  }

  .cscse-callout-note.listed {
    background: #f0fdf4;
    color: #166534;
  }

  .cscse-callout-note.not-found {
    background: #f8fafc;
    color: #475569;
  }

  .card-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .selected-card-official {
    overflow-wrap: anywhere;
  }

  /* Large screens only: overlay the card on the map's lower-left corner.
     Short viewports (<=700px) keep the card in normal flow. */
  @media (min-width: 1024px) and (min-height: 701px) {
    .map-selected-region {
      position: absolute;
      left: 32px;
      right: 32px;
      bottom: 32px;
      margin-top: 0;
      z-index: 20;
    }
    .map-selected-card {
      max-width: 420px;
    }
  }

  .btn-sm {
    padding: 0.3rem 0.6rem;
    font-size: 0.8rem;
    min-height: 30px;
  }

  .school-pick-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .school-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .school-dot.listed {
    background: #059669;
  }

  .school-dot.not-found {
    background: #94a3b8;
  }

  :global(.maplibre-pin) {
    width: 44px;
    height: 44px;
    border-radius: 50% 50% 50% 0;
    transform: rotate(-45deg);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  :global(.maplibre-pin.cscse-operator-listed),
  :global(.maplibre-pin.cscse-listed) {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    border: 2px solid #ffffff;
    box-shadow: 0 2px 6px rgba(5, 150, 105, 0.45);
  }

  :global(.maplibre-pin.cscse-operator-listed:hover),
  :global(.maplibre-pin.cscse-listed:hover) {
    transform: rotate(-45deg) scale(1.15);
    box-shadow: 0 4px 10px rgba(5, 150, 105, 0.6);
    z-index: 50;
  }

  :global(.maplibre-pin.cscse-operator-absent),
  :global(.maplibre-pin.cscse-not-found) {
    background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%);
    border: 2px solid #ffffff;
    box-shadow: 0 2px 5px rgba(100, 116, 139, 0.35);
  }

  :global(.maplibre-pin.cscse-operator-absent:hover),
  :global(.maplibre-pin.cscse-not-found:hover) {
    transform: rotate(-45deg) scale(1.15);
    box-shadow: 0 4px 8px rgba(100, 116, 139, 0.5);
    z-index: 50;
  }

  :global(.maplibre-pin.selected) {
    background: #e11d48 !important;
    border-color: #ffffff;
    transform: rotate(-45deg) scale(1.35) !important;
    box-shadow: 0 0 0 4px rgba(225, 29, 72, 0.35), 0 6px 14px rgba(0, 0, 0, 0.35);
    z-index: 100 !important;
  }

  :global(.maplibre-pin:focus-visible) {
    outline: 3px solid var(--color-focus);
    outline-offset: 3px;
  }

  :global(.maplibre-cluster) {
    width: 44px;
    height: 44px;
    border: 3px solid #fff;
    border-radius: 50%;
    background: #0f3d64;
    color: #fff;
    box-shadow: 0 3px 9px rgba(15, 61, 100, 0.38);
    cursor: zoom-in;
    padding: 0;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  :global(.maplibre-cluster:hover) {
    transform: scale(1.1);
    box-shadow: 0 5px 14px rgba(15, 61, 100, 0.48);
  }

  :global(.maplibre-cluster.selected) {
    background: #e11d48;
    box-shadow: 0 0 0 4px rgba(225, 29, 72, 0.3), 0 5px 14px rgba(15, 23, 42, 0.35);
  }

  :global(.maplibre-cluster:focus-visible) {
    outline: 3px solid var(--color-focus);
    outline-offset: 3px;
  }

  :global(.maplibre-cluster-inner) {
    font-size: 0.85rem;
    font-weight: 800;
    line-height: 1;
    pointer-events: none;
  }

  :global(.maplibre-pin-inner) {
    transform: rotate(45deg);
    color: #fff;
    font-size: 11px;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }
</style>

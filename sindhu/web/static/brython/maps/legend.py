from html import escape as escape_html

from browser import window

from stations import metric_infos


class LegendMixin:
    def set_interpolation_legend(self, legend):
        """Draw the color scale of the interpolated surface as a gradient bar."""
        from browser import document as doc

        container = self._interpolation_legend_container
        if container is None:
            container = doc.createElement("div")
            # map-ui: hidden with the other floating cards in map focus mode
            container.className = "map-ui map-scale-legend"
            self.map.getContainer() <= container
            self._interpolation_legend_container = container
            self.leaflet.DomEvent.disableClickPropagation(container)
            self.leaflet.DomEvent.disableScrollPropagation(container)

        if not legend:
            container.html = ""
            return

        # Sizes are inline styles: Tailwind only ships classes it finds in the
        # templates, and it never scans these Brython sources
        bands = legend.get("bands") or []
        chips = "".join(
            f'<span style="flex:1 1 0;background-color:{band["color"]};"></span>'
            for band in bands
        )

        # Labels sit at their own band edge; the end ones are pulled inside the
        # bar so they do not overflow the legend box
        ticks = ""
        for tick in legend.get("ticks") or []:
            percent = round(tick["offset"] * 100)
            shift = "0" if percent == 0 else ("-100%" if percent >= 99 else "-50%")
            ticks += (
                f'<span style="position:absolute;white-space:nowrap;font-size:9px;'
                f'color:var(--color-ink-500);left:{percent}%;transform:translateX({shift});">'
                f'{tick["value"]:g}</span>'
            )

        container.html = f"""
        <div class="bg-base-100/95 backdrop-blur-sm border border-ink-200 rounded-xl shadow-md px-3 py-2">
            <div style="font-size:11px;font-weight:600;color:var(--color-ink-700);line-height:1.2;">{legend.get("title", "")}</div>
            <div style="display:flex;height:10px;margin-top:6px;border:1px solid var(--color-ink-300);border-radius:3px;overflow:hidden;">{chips}</div>
            <div style="position:relative;height:13px;margin-top:2px;">{ticks}</div>
            <div style="font-size:9px;color:var(--color-ink-500);text-align:right;">{legend.get("unit", "")}</div>
        </div>
        """

    def set_legend(self, levels, title, subtitle=""):
        """Let the caller own the legend when markers are not coloured by a
        metric scale — the water monitor colours them by risk instead."""
        self._legend_override = True
        self.render_legend(levels, title, subtitle)

    async def update_metric_legend(self, document_id):
        """Draw the colour scale of the active metric on top of the map.

        The bands come from `metric_infos.get_metric_levels`, which reads the
        same `metric_colors` ranks the markers use, so the legend can never
        describe colours the map does not actually draw.
        """
        if self._legend_override:
            # A caller already put its own scale there; leave it alone
            self.metric_legends[document_id] = True
            return

        metric_type = document_id.replace("empirical_", "").lower()
        levels = metric_infos.get_metric_levels(metric_type)
        if not levels:
            self.metric_legends[document_id] = True
            return

        self.render_legend(
            levels,
            metric_infos.get_metric_level_title(metric_type),
            "ระดับความปลอดภัย",
        )
        self.metric_legends[document_id] = True

    def refresh_legend(self):
        """Redraw the legend with its last levels, e.g. after zones load."""
        args = getattr(self, "_legend_args", None)
        if args:
            self.render_legend(*args)

    def zone_legend_html(self):
        """Legend rows for the zone outlines, kept apart from the risk colours."""
        entries = self.visible_zone_legend_entries()
        if not entries:
            return ""
        rows = ""
        for entry in entries:
            dash = f' stroke-dasharray="{entry["dash"]}"' if entry["dash"] else ""
            rows += f"""
            <div class="flex items-center gap-2">
                <svg width="22" height="8" viewBox="0 0 22 8" class="shrink-0" aria-hidden="true">
                    <line x1="0" y1="4" x2="22" y2="4" stroke="#141414" stroke-width="5"/>
                    <line x1="0" y1="4" x2="22" y2="4" stroke="{entry["color"]}" stroke-width="2.6"{dash}/>
                </svg>
                <span class="text-[11px] text-ink-700 leading-tight">{escape_html(entry["name"])}</span>
            </div>
            """
        return f"""
            <div class="mt-1.5 pt-1.5 border-t border-ink-100">
                <div class="text-[10px] font-semibold text-ink-600">ขอบเขตโซน</div>
                <div class="text-[9px] text-ink-400 mb-1">สีพื้นในโซน = ระดับความเสี่ยงสูงสุดในโซน</div>
                <div class="flex flex-col gap-1">{rows}</div>
            </div>
        """

    LEGEND_COLLAPSED_KEY = "sindhu_monitor_legend_collapsed"

    def legend_starts_collapsed(self):
        """Folded on phones and tablets, where it covers too much of the map,
        unless the viewer already chose otherwise on this device."""
        try:
            saved = window.localStorage.getItem(self.LEGEND_COLLAPSED_KEY)
        except Exception:
            saved = None
        if saved in ("0", "1"):
            return saved == "1"
        try:
            return not window.matchMedia("(min-width: 1024px)").matches
        except Exception:
            return False

    def legend_html(self, levels, title, subtitle="", collapsed=False):
        """Legend card: the full key, or a small chip of the risk colours."""
        swatches = "".join(
            f'<span class="inline-block w-2.5 h-2.5 rounded-sm" style="background-color: {level["color"]};"></span>'
            for level in levels
        )
        if collapsed:
            return f"""
        <button type="button" class="map-legend-toggle flex items-center gap-1.5 bg-base-100/95 backdrop-blur-sm border border-ink-200 rounded-full shadow-md pl-2.5 pr-2 py-1.5 cursor-pointer hover:border-brand-400"
            aria-expanded="false" aria-label="แสดงคำอธิบายสี: {title}" title="แสดงคำอธิบายสี">
            <i class="ph ph-palette text-brand-600 text-sm" aria-hidden="true"></i>
            <span class="flex items-center gap-0.5" aria-hidden="true">{swatches}</span>
            <i class="ph ph-caret-up text-ink-500 text-xs" aria-hidden="true"></i>
        </button>
        """

        rows = ""
        for level in levels:
            rows += f"""
            <div class="flex items-center gap-2">
                <span class="inline-block w-4 h-3 rounded-sm shrink-0 border border-ink-300" style="background-color: {level["color"]};"></span>
                <span class="text-[11px] text-ink-700 leading-tight">{level["label"]}</span>
                <span class="text-[10px] text-ink-400 leading-tight ml-auto pl-2 whitespace-nowrap">{level["range"]}</span>
            </div>
            """

        subtitle_html = ""
        if subtitle:
            subtitle_html = f'<div class="text-[9px] text-ink-400">{subtitle}</div>'

        return f"""
        <div class="bg-base-100/95 backdrop-blur-sm border border-ink-200 rounded-xl shadow-md px-3 py-2">
            <button type="button" class="map-legend-toggle w-full flex items-center gap-1.5 pb-1 mb-1.5 border-b border-ink-100 text-left cursor-pointer"
                aria-expanded="true" aria-label="ย่อคำอธิบายสี" title="ย่อคำอธิบายสี">
                <i class="ph ph-palette text-brand-600 text-sm" aria-hidden="true"></i>
                <div class="leading-tight min-w-0 flex-1">
                    <div class="text-[11px] font-semibold text-ink-700">{title}</div>
                    {subtitle_html}
                </div>
                <i class="ph ph-caret-down text-ink-500 text-xs" aria-hidden="true"></i>
            </button>
            <div class="flex flex-col gap-1">
                {rows}
            </div>
            {self.zone_legend_html()}
            {self.rivers_status_html()}
        </div>
        """

    def rivers_status_html(self):
        if not getattr(self, "rivers_unavailable", False):
            return ""
        return """
            <div class="mt-1.5 pt-1.5 border-t border-ink-100 text-[10px] text-warning flex items-center gap-1">
                <i class="ph ph-warning text-xs" aria-hidden="true"></i>
                <span>โหลดเส้นแม่น้ำไม่สำเร็จ</span>
            </div>
        """

    def render_legend(self, levels, title, subtitle=""):
        from browser import document as doc

        self._legend_args = (levels, title, subtitle)
        if getattr(self, "_legend_collapsed", None) is None:
            self._legend_collapsed = self.legend_starts_collapsed()

        container = self._metric_legend_container
        if container is None:
            container = doc.createElement("div")
            # map-ui: hidden with the other floating cards in map focus mode
            container.className = "map-ui map-legend"
            self.map.getContainer() <= container
            self._metric_legend_container = container
            # Keep clicks and wheel events on the legend out of the map
            self.leaflet.DomEvent.disableClickPropagation(container)
            self.leaflet.DomEvent.disableScrollPropagation(container)

        container.html = self.legend_html(
            levels, title, subtitle, collapsed=self._legend_collapsed
        )
        toggle = container.select_one(".map-legend-toggle")
        if toggle:
            toggle.bind("click", self._on_legend_toggle)
        reset = getattr(self, "_reset_btn_container", None)
        if reset is not None and reset.style.display != "none":
            self._lift_reset_button_over_legends()

    def _on_legend_toggle(self, event=None):
        self._legend_collapsed = not self._legend_collapsed
        try:
            window.localStorage.setItem(
                self.LEGEND_COLLAPSED_KEY, "1" if self._legend_collapsed else "0"
            )
        except Exception:
            pass
        self.refresh_legend()
        # The card was redrawn: keep keyboard focus on its toggle.
        container = self._metric_legend_container
        toggle = container.select_one(".map-legend-toggle") if container else None
        if toggle:
            toggle.focus()

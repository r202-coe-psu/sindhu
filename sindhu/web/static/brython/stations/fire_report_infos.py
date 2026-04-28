ALL_FIRE_REPORT_NAMES = ["FAHP", "dNBR", "aod", "MLBA", "Emissions"]
FIRE_REPORT_NAMES = ["FAHP", "dNBR", "MLBA"]
HTML_FIRE_REPORT_LEGENDS = dict(
    fahp=[
        {"DES": "พื้นที่เสี่ยงตํ่ามาก", "fill": "#003300"},
        {"DES": "พื้นที่เสี่ยงตํ่า", "fill": "#66FF00"},
        {"DES": "พื้นที่เสี่ยงปานกลาง", "fill": "#FFFF99"},
        {"DES": "พื้นที่เสี่ยงสูง", "fill": "#FFD700"},
        {"DES": "พื้นที่เสี่ยงสูงมาก", "fill": "#FF0000"},
    ],
    dnbr=[{"DES": "Unburned", "fill": "#228B22"}, {"DES": "Burned", "fill": "#FF0000"}],
    aod=[
        {"DES": "0", "fill": "#FFFFFF"},
        {"DES": "0.2", "fill": "#FFF5E1"},
        {"DES": "0.4", "fill": "#F4D88A"},
        {"DES": "0.6", "fill": "#E8A857"},
        {"DES": "0.8", "fill": "#BE5B2D"},
        {"DES": "1.0", "fill": "#5E2D16"},
    ],
    mlba=[
        {"DES": "พื้นที่เสี่ยงตํ่ามาก", "fill": "#003300"},
        {"DES": "พื้นที่เสี่ยงตํ่า", "fill": "#66FF00"},
        {"DES": "พื้นที่เสี่ยงปานกลาง", "fill": "#FFFF99"},
        {"DES": "พื้นที่เสี่ยงสูงมาก", "fill": "#FF0000"},
    ],
    emissions=[
        {"fill": "#F2F2F2", "DES": "0 - 1"},
        {"fill": "#CDCDFF", "DES": "1 - 5"},
        {"fill": "#FFFF94", "DES": "5 - 10"},
        {"fill": "#FF9A9A", "DES": "10 - 20"},
        {"fill": "#ED3000", "DES": "20 - 50"},
        {"fill": "#743030", "DES": "50 - 100"},
        {"fill": "#7030A0", "DES": "100 - 1000"},
    ],
)

HTML_FIRE_REPORT_LEGEND_TITLES = dict(
    fahp="FAHP Legend",
    dnbr="dNBR Legend",
    aod="AOD Legend",
    mlba="MLBA Legend",
    emissions="PM<sub>2.5</sub> Emissions<br>tons/yr/grid",
)


def get_fire_report_style(report_name):
    return {
        "fillOpacity": 0.9 if report_name in FIRE_REPORT_NAMES else 1,
        "fill": True,
        "color": "gray" if report_name in FIRE_REPORT_NAMES else "white",
        "stroke": True,
        "weight": 0.4 if report_name in FIRE_REPORT_NAMES else 0.1,
        "opacity": 1,
    }


def get_fire_report_popup(report_name):
    return "DES" if report_name in FIRE_REPORT_NAMES else "Level"

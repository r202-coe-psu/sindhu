from browser import document, window
from javascript import JSON


class TreemapChart:
    def __init__(self, datum):
        self.apexcharts = window.ApexCharts
        self.datum = JSON.parse(datum)
        # ############################################# Pie chart
        # labels = []
        # series = []
        # for data in self.datum:
        #     labels.append(data["_id"])
        #     series.append(data["total"])
        # self.options = {
        #     "chart": {"type": "donut", "height": 350},
        #     "series": series,
        #     "labels": labels,
        #     "dataLabels": {
        #         "enabled": True  # , "formatter": lambda val, zx: f"{val:.2f}%"
        #     },
        #     "plotOptions": {
        #         "pie": {
        #             "customScale": 1,
        #             "donut": {
        #                 "labels": {
        #                     "show": True,
        #                     "name": {
        #                         "show": True,
        #                     },
        #                     "value": {
        #                         "show": True,
        #                     },
        #                     "total": {
        #                         "show": True,
        #                         "label": "รวม",
        #                     },
        #                 },
        #             },
        #         },
        #     },
        # }
        # ############################################# Pie chart

        self.options = {
            "chart": {
                "height": 600,
                "type": "treemap",
            },
            "series": [
                {"data": self.datum},
            ],
            "colors": [
                "#F7B844",
                "#ADD8C7",
                "#CDD7B6",
                "#C1F666",
                "#C0ADDB",
            ],
            "plotOptions": {"treemap": {"distributed": True, "enableShades": False}},
            "title": {
                "text": "รายงานสาเหตุที่ที่เกิดไฟไหม้ทั้งหมด",
                "align": "center",
            },
            "dataLabels": {
                "enabled": True,
                "style": {
                    "fontSize": "30px",
                    "fontWeight": "bold",
                    "colors": ["#634848"],
                },
            },
        }

    def start(self):
        self.chart = self.apexcharts.new(document["pie-causes-chart"], self.options)
        self.chart.render()

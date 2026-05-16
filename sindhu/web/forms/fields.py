from wtforms import fields, widgets


class GeoField(fields.Field):
    widget = widgets.TextInput()

    def _value(self):
        if self.data:
            return ", ".join([str(d) for d in self.data])
        else:
            return ""

    def process_formdata(self, valuelist):
        if valuelist:
            self.data = [float(x.strip()) for x in valuelist[0].split(",")]
        else:
            self.data = []

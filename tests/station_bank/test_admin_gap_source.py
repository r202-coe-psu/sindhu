import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRYTHON_ROOT = ROOT / "sindhu" / "web" / "static" / "brython"
TEMPLATE = ROOT / "sindhu" / "web" / "templates" / "stations" / "index.html"
if str(BRYTHON_ROOT) not in sys.path:
    sys.path.append(str(BRYTHON_ROOT))

from stations import bank_status  # noqa: E402

NODE = shutil.which("node")

PYTHON_TO_ADMIN_SOURCE = {
    bank_status.GAP_FROM_ADMIN: "admin",
    bank_status.GAP_FROM_ETL_DIFF: "etl_diff",
    bank_status.GAP_FROM_ETL_BANK: "etl_bank",
    None: "none",
}

DWR_METADATA = {"zflowMsl": 8.0, "lbMsl": 12.5, "rbMsl": 12.0}

CASES = {
    "admin bank": ("rid", 12.0, {"water_level_critical": 11.0}, {"waterlevel": 11.6}),
    "admin bank, diff present": (
        "rid",
        12.0,
        {"water_level_critical": 11.0},
        {"waterlevel": 11.6, "diff_wl_bank": 0.6},
    ),
    "etl diff": (
        "rid",
        None,
        {"water_level_critical": 12.0},
        {"waterlevel": 11.6, "diff_wl_bank": -0.5},
    ),
    "etl bank": (
        "thaiwater",
        None,
        {"water_level_critical": 12.0},
        {"waterlevel": 11.6},
    ),
    "nothing": ("rid", None, {}, {"waterlevel": 11.6}),
    "dead sensor with derived diff": (
        "rid",
        None,
        {},
        {"waterlevel": -9.99, "diff_wl_bank": -22.99},
    ),
    "rid diff equal to the level": (
        "rid",
        None,
        {},
        {"waterlevel": 11.6, "diff_wl_bank": 11.6},
    ),
    "rid diff on a zero bank": (
        "rid",
        None,
        {"water_level_critical": 0},
        {"waterlevel": 11.6, "diff_wl_bank": 3.0},
    ),
    "implausible admin bank": (
        "rid",
        120.0,
        {"water_level_critical": 12.0},
        {"waterlevel": 11.6},
    ),
    "zero admin bank": ("rid", 0, {"water_level_critical": 12.0}, {"waterlevel": 11.6}),
    "stored dead admin bank": ("rid", -9.99, {}, {"waterlevel": 11.6}),
    "dwr with gauge zero": ("dwr", None, DWR_METADATA, {"waterlevel": 3.6}),
    "dwr admin bank": ("dwr", 12.2, DWR_METADATA, {"waterlevel": 3.6}),
    "dwr admin bank without gauge zero": (
        "dwr_telemetry",
        12.2,
        {},
        {"waterlevel": 3.6, "diff_wl_bank": -0.7},
    ),
    "dwr without anything": ("dwr", None, {}, {"waterlevel": 3.6}),
    "msl metric": ("dwr", 12.0, {}, {"waterlevel_msl": 11.6}),
}


def _station(source, bank_level, metadata, metrics):
    return {
        "id": "s",
        "source": source,
        "bank_level": bank_level,
        "metadata": metadata,
        "metrics": [{"metric_type": k, "value": v} for k, v in metrics.items()],
    }


def _admin_script():
    source = TEMPLATE.read_text(encoding="utf-8")
    script = source[source.index("<script>") + len("<script>") :]
    script = script[: script.index("</script>")]
    script = re.sub(r"\{#.*?#\}", "", script, flags=re.S)
    script = re.sub(r"\{\{.*?\}\}", "", script)
    start = script.index("const BANK_LEVEL_MIN")
    end = script.index("function findIssues")
    constants_start = script.index("const SOURCE_LABELS")
    constants_end = script.index("let stations")
    return script[constants_start:constants_end] + script[start:end]


@unittest.skipUnless(NODE, "node is not installed")
class AdminGapSourceParityTests(unittest.TestCase):
    def test_admin_page_picks_the_same_source_as_the_map(self):
        stations = {name: _station(*case) for name, case in CASES.items()}
        program = (
            _admin_script()
            + "\nconst stations = "
            + json.dumps(stations)
            + ";\nconst out = {};\n"
            + "for (const [name, s] of Object.entries(stations)) out[name] = gapSource(s);\n"
            + "console.log(JSON.stringify(out));\n"
        )
        completed = subprocess.run(
            [NODE, "-e", program], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        from_admin_page = json.loads(completed.stdout)

        for name, station in stations.items():
            with self.subTest(case=name):
                _, source = bank_status.station_gap(station)
                self.assertEqual(from_admin_page[name], PYTHON_TO_ADMIN_SOURCE[source])


if __name__ == "__main__":
    unittest.main()

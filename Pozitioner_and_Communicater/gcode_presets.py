DEFAULT_SETTINGS = {
    "motor_current": 800,
    "acceleration": 500,
    "jerk": 10,
    "feedrate": 1500,
    "steps_per_mm": {
        "X": 80.00,
        "Y": 80.00,
        "Z": 400.00,
        "E": 93.00
    },
    "home_position": {
        "X": 0,
        "Y": 0,
        "Z": 0
    },
    "max_feedrate": {
        "X": 500,
        "Y": 500,
        "Z": 5,
        "E": 25
    },
    "max_acceleration": {
        "X": 500,
        "Y": 500,
        "Z": 100,
        "E": 10000
    }
}

MARLIN_COMMAND_MAP = {
    "steps_per_mm": {
        "cmd": "M92",
        "axes": "XYZE",
        "type": "dict"
    },
    "motor_current": {
        "cmd": "M906",
        "axes": "XYZE",
        "type": "value"
    },
    "acceleration": {
        "cmd": "M204",
        "format": lambda v: f"P{v} T{v}"
    },
    "jerk": {
        "cmd": "M205",
        "axes": "XYZE",
        "type": "value"
    },
    "max_feedrate": {
        "cmd": "M203",
        "axes": "XYZE",
        "type": "dict"
    },
    "max_acceleration": {
        "cmd": "M201",
        "axes": "XYZE",
        "type": "dict"
    },
    "feedrate": {
        "cmd": "G1",
        "format": lambda v: f"F{v}"   #format(1500) → "F1500"
    },
    "home_position": {
        "cmd": "G92",
        "axes": "XYZ",
        "type": "dict"
    }
}

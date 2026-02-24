
DEFAULT_ROOT = "/ref/dc14/PDF/STATS"
DEFAULT_NETWORK = "BK"
DEFAULT_LOCATION = "00"

DEFAULT_STATIONS = ("BKS", "THOM")   # e.g. ("BKS", "AASB")
DEFAULT_COMPONENTS = ("HHE", "HHN", "HHZ", "HNE", "HNN", "HNZ")     # e.g. ("HHZ", "HHN", "HHE")

# None => accept any year/day
DEFAULT_START_YEAR = 2025           # e.g. 2026 for 2026.*
DEFAULT_START_DAY = 1      # e.g. 5  for 2026.005

DEFAULT_END_YEAR = 2025
DEFAULT_END_DAY = 366        # e.g. 334 for 2026.334

# e.g. [0.05, 0.10, 0.25] for 5th, 10th, and 25th percentiles
DEFAULT_PERCENTILES = [0.05, 0.10]

"""Fixed places the simulated data and the live demo kit share (all real Liverpool streets, from OpenStreetMap).

The demo kit photos carry these positions in their GPS data, so the seed builder puts the matching hotspot and the
merge target at the same spots. Change them together.
"""

# Repeat hotspots: (street, lat, lon, past reports in the last 90 days, older reports over the two years before)
HOTSPOTS = [
    ("Makin Street", 53.444103, -2.970340, 13, 30),   # demo photo 4 lands here: "Crew today" on a repeat hotspot
    ("Lodge Lane", 53.394902, -2.949456, 8, 22),      # the top card in the queue, growing this week
    ("Granby Street", 53.393554, -2.957364, 5, 18),
    ("Kensington", 53.411873, -2.953048, 6, 20),
    ("Picton Road", 53.400806, -2.930769, 4, 24),      # student area: the June move-out peak
    ("Breck Road", 53.423163, -2.958455, 5, 16),
    ("County Road", 53.440520, -2.970823, 4, 14),
    ("Boaler Street", 53.416130, -2.952190, 3, 12),
    ("Park Road", 53.385096, -2.965212, 3, 12),
    ("Rice Lane", 53.455108, -2.961698, 3, 10),
]
GROWING = {"Lodge Lane"}  # a few extra reports this week, so the card shows "Growing"

# The open report that demo photo 5 lands beside (9 m north), so the app asks whether it is the same.
MERGE_PLACE = ("Belmont Road", 53.423382, -2.951165)
MERGE_KIT_OFFSET_LAT = 0.00008

# The live demo kit: (file, source photo, lat, lon, street, what should happen)
KIT = [
    ("1_black_bags_jubilee_drive.jpg", "case_052", 53.408318, -2.954416, "Jubilee Drive", "Officer to inspect"),
    ("2_fridge_lawrence_road.jpg", "case_019", 53.397012, -2.934881, "Lawrence Road", "Not fly-tipping: bulky collection booked"),
    ("3_paint_tins_oglet_lane.jpg", "case_094", 53.328931, -2.833539, "Oglet Lane", "Specialist removal"),
    ("4_mattress_makin_street.jpg", "case_085", 53.444103, -2.970340, "Makin Street", "Crew today, on a repeat hotspot"),
    ("5_optional_merge_belmont_road.jpg", "case_115", MERGE_PLACE[1] + MERGE_KIT_OFFSET_LAT, MERGE_PLACE[2], "Belmont Road",
     "Asks if it is the same as the open report; yes adds a still-there confirmation"),
]
KIT_SOURCES = {k[1] for k in KIT}

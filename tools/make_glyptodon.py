"""Write vehicles/glyptodon.json, Das Glyptodon (two-door), from a few dimensions.

Usage: python3 tools/make_glyptodon.py && tools/preview_vehicle.sh vehicles/glyptodon.json

The two-door cab on the 3.25 m wheelbase, with the spare lying under the bed front on the
left. Everything else is the family's, in tools/glyptodon_family.py.
"""
import glyptodon_family

glyptodon_family.write({
    "codename": "Glyptodon",
    "displayName": "Das Glyptodon",
    "description": "Das Glyptodon traded the round nose for a square jaw and never looked back. Long frame, long bed, a cab with corners you could set a ruler on, and a gearbox arrangement it will explain to you at length whether you asked or not. Armoured by temperament, if not by law.",
    "listing": {
        "family": "Glyptodon", "variant": "two-door",
        "real": {"make": "Mercedes-Benz", "model": "Unimog U 1300 L", "series": "435", "variant": "two-door cab",
                 "years": "",
                 "description": "A two-door truck of the 435 series with an angular cab on a 3.25 m wheelbase and a 1.86 m track, on 14.5R20 tyres (1090 mm across). Steel drop-side bed, black plastic fender flares, slatted black grille, black steel bumper carrying the headlamps, and a raised air intake on the right A-pillar.",
                 "basis": "Modelled from photos and a dimensioned drawing: wheelbase, track, tyre size, bed length and ride height follow them."},
    },
    "itemId": 3000000003,
    "wheelbase": 3.25,
})

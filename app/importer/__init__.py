"""Company import: parse and validate import files, then load them into the database.

`parse.parse_bundle` checks everything and produces a preview (row counts and
errors) without touching the database. `load.load_company` writes a validated
bundle. The startup seed and the Import page both use these same two steps.
"""

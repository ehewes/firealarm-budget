"""Shared pieces of the EdenMatrix go backend.

Kept deliberately small: only what the API and the scraper must agree on lives
here (settings, the database pool, the queue and its job shapes, URL rules, spend
caps, session codes). Anything only one service uses stays in that service.
"""

# -*- coding: utf-8 -*-
"""1.3.0: the recruiter dashboard moved from the website (/recruiter) into the
Recruitment app. Remove the old website menu, including per-website copies."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    menus = env['website.menu'].search([('url', 'in', ['/recruiter', '/recruiter/'])])
    menus.unlink()

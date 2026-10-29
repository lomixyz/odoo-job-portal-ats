# -*- coding: utf-8 -*-
from odoo import models

CANDIDATE_URL = '/my/jobs'


def _matches(menu_url, prefix):
    url = (menu_url or '').split('?')[0].split('#')[0].rstrip('/')
    if '://' in url:  # absolute link to this site
        url = '/' + url.split('://', 1)[1].partition('/')[2]
    return url == prefix or url.startswith(prefix + '/')


class WebsiteMenu(models.Model):
    _inherit = 'website.menu'

    def _compute_visible(self):
        """Candidate Dashboard menu: signed-in users only.

        The website header is cached per website and per "public user or not",
        so visibility must depend on nothing else.
        """
        super()._compute_visible()
        if self.env.user._is_public():
            for menu in self:
                if _matches(menu.url, CANDIDATE_URL):
                    menu.is_visible = False

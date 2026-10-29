# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    aa_job_portal_redirect_home = fields.Boolean(
        'Open Candidate Dashboard as Portal Home',
        config_parameter='aa_job_portal.redirect_home',
        help='Job seekers who open /my are sent straight to their candidate dashboard.')

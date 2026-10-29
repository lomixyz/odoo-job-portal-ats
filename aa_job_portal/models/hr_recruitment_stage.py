# -*- coding: utf-8 -*-
from odoo import fields, models


class HrRecruitmentStage(models.Model):
    _inherit = 'hr.recruitment.stage'

    aa_portal_shortlist = fields.Boolean(
        'Shortlisted in Candidate Portal',
        help='Applications in this stage count as "Shortlist" on the candidate dashboard.')
    aa_portal_label = fields.Char(
        'Candidate-facing Label', translate=True,
        help='Status shown to candidates instead of the internal stage name.')

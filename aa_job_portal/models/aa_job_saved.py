# -*- coding: utf-8 -*-
from odoo import fields, models


class AaJobSaved(models.Model):
    _name = 'aa.job.saved'
    _description = 'Saved Job (Candidate Portal)'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one('res.partner', 'Candidate', required=True, ondelete='cascade', index=True)
    job_id = fields.Many2one('hr.job', 'Job Position', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='job_id.company_id', store=True)

    _sql_constraints = [
        ('partner_job_uniq', 'unique(partner_id, job_id)', 'This job is already saved.'),
    ]

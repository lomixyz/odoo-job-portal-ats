# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AaJobNotification(models.Model):
    _name = 'aa.job.notification'
    _description = 'Candidate Portal Notification'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one('res.partner', 'Candidate', required=True, ondelete='cascade', index=True)
    title = fields.Char(required=True)
    body = fields.Text()
    notif_type = fields.Selection([
        ('application', 'Application'),
        ('status', 'Status Update'),
        ('interview', 'Interview'),
        ('info', 'Information'),
    ], string='Type', default='info', required=True)
    applicant_id = fields.Many2one('hr.applicant', ondelete='cascade', index=True)
    job_id = fields.Many2one('hr.job', ondelete='set null')
    event_id = fields.Many2one('calendar.event', 'Interview', ondelete='set null')
    url = fields.Char('Link')
    is_read = fields.Boolean('Read', default=False, index=True)

    @api.model
    def _aa_notify(self, partner, title, body=False, notif_type='info', applicant=False, event=False, url=False):
        if not partner:
            return self.browse()
        return self.sudo().create({
            'partner_id': partner.id,
            'title': title,
            'body': body or False,
            'notif_type': notif_type,
            'applicant_id': applicant.id if applicant else False,
            'job_id': applicant.job_id.id if applicant and applicant.job_id else False,
            'event_id': event.id if event else False,
            'url': url or False,
        })

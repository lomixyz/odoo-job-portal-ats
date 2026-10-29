# -*- coding: utf-8 -*-
from odoo import _, api, models


class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        events._aa_notify_candidate(rescheduled=False)
        return events

    def write(self, vals):
        res = super().write(vals)
        if {'start', 'stop', 'allday'} & set(vals):
            self._aa_notify_candidate(rescheduled=True)
        return res

    def _aa_notify_candidate(self, rescheduled=False):
        Notification = self.env['aa.job.notification'].sudo()
        for event in self.sudo().filtered('applicant_id'):
            applicant = event.applicant_id
            if not applicant._aa_is_portal_tracked():
                continue
            job_name = applicant.job_id.name or event.name
            if rescheduled:
                title = _('Interview rescheduled: %s', job_name)
            else:
                title = _('Interview scheduled: %s', job_name)
            Notification._aa_notify(applicant.partner_id, title, event.name, 'interview',
                                    applicant=applicant, event=event, url='/my/jobs/interviews')

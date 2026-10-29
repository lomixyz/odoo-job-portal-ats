# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    aa_portal_applied = fields.Boolean('Applied via Candidate Portal', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Candidate-facing status
    # ------------------------------------------------------------------
    def _aa_portal_status(self):
        """Return (label, tone) shown to the candidate. Tone is a CSS modifier."""
        self.ensure_one()
        status = self.application_status
        if status == 'refused':
            return _('Not selected'), 'danger'
        if status == 'hired':
            return _('Hired'), 'success'
        if status == 'archived':
            return _('Closed'), 'muted'
        stage = self.stage_id
        label = stage.aa_portal_label or stage.name or _('Submitted')
        return label, 'shortlist' if stage.aa_portal_shortlist else 'progress'

    def _aa_is_portal_tracked(self):
        self.ensure_one()
        return bool(self.partner_id) and (self.aa_portal_applied or self.partner_id.aa_job_seeker)

    # ------------------------------------------------------------------
    # Website form: one active application per candidate and job
    # ------------------------------------------------------------------
    def website_form_input_filter(self, request, values):
        values = super().website_form_input_filter(request, values)
        if values.get('job_id'):
            job = self.env['hr.job'].sudo().browse(int(values['job_id'])).exists()
            if job and job._aa_is_filled():
                raise UserError(_('This position has been filled and no longer accepts applications.'))
        user = request.env.user
        if values.get('job_id') and not user._is_public():
            domain = [('job_id', '=', int(values['job_id'])), ('partner_id', '=', user.partner_id.id)]
            if user.partner_id.email:
                domain = ['&', ('job_id', '=', int(values['job_id'])), '|',
                          ('partner_id', '=', user.partner_id.id),
                          ('email_from', '=ilike', user.partner_id.email.strip())]
            if self.sudo().search_count(domain):
                raise UserError(_('You have already applied for this job. '
                                  'You can follow it from your Candidate Dashboard.'))
        return values

    # ------------------------------------------------------------------
    # Hiring cannot exceed the job position's target
    # ------------------------------------------------------------------
    def _aa_check_hire_target(self, stage_id):
        stage = self.env['hr.recruitment.stage'].browse(stage_id)
        if not stage.hired_stage:
            return
        newly_hired = self.filtered(lambda a: a.job_id and not a.stage_id.hired_stage and not a.date_closed)
        for job in newly_hired.job_id:
            limit = job.sudo()._aa_hire_limit()
            count = len(newly_hired.filtered(lambda a: a.job_id == job))
            if limit is not None and count > limit:
                raise UserError(_(
                    'The position "%(job)s" is already filled: %(hired)s hired for a target of %(target)s.\n'
                    'Increase the Target on the job position before hiring more applicants.',
                    job=job.name,
                    hired=job.sudo()._aa_hired_counts().get(job.id, 0),
                    target=job.sudo()._aa_total_target(job.sudo()._aa_hired_counts().get(job.id, 0)),
                ))

    # ------------------------------------------------------------------
    # Notifications on status changes
    # ------------------------------------------------------------------
    def write(self, vals):
        if vals.get('stage_id') and not self.env.context.get('aa_allow_over_target'):
            self._aa_check_hire_target(vals['stage_id'])
        watched = {'stage_id', 'active', 'refuse_reason_id'} & set(vals)
        before = {}
        if watched:
            for applicant in self:
                before[applicant.id] = (applicant.stage_id.id, applicant.application_status)
        res = super().write(vals)
        if watched:
            self._aa_notify_status_change(before)
        return res

    def _aa_notify_status_change(self, before):
        Notification = self.env['aa.job.notification'].sudo()
        for applicant in self.sudo().with_context(active_test=False):
            if applicant.id not in before or not applicant._aa_is_portal_tracked():
                continue
            old_stage_id, old_status = before[applicant.id]
            if old_stage_id == applicant.stage_id.id and old_status == applicant.application_status:
                continue
            job_name = applicant.job_id.name or _('your application')
            label, _tone = applicant._aa_portal_status()
            if applicant.application_status == 'refused':
                title = _('Update on %s', job_name)
                body = _('Thank you for your interest. The company decided not to move forward with your application.')
            elif applicant.application_status == 'hired':
                title = _('Congratulations! You were hired for %s', job_name)
                body = False
            elif applicant.stage_id.aa_portal_shortlist and old_status == 'ongoing' and \
                    not self.env['hr.recruitment.stage'].browse(old_stage_id).aa_portal_shortlist:
                title = _('You have been shortlisted for %s', job_name)
                body = _('Current status: %s', label)
            else:
                title = _('Your application for %s moved to "%s"', job_name, label)
                body = False
            Notification._aa_notify(applicant.partner_id, title, body, 'status',
                                    applicant=applicant, url='/my/jobs/applied')

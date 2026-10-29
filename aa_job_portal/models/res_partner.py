# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.http import request
from odoo.tools import format_datetime


class ResPartner(models.Model):
    _inherit = 'res.partner'

    aa_job_seeker = fields.Boolean('Job Seeker', copy=False,
                                   help='Set automatically when the contact opens the candidate dashboard.')
    aa_profile_verified = fields.Boolean('Candidate Profile Verified', copy=False)
    aa_headline = fields.Char('Desired Position')
    aa_skills = fields.Char('Key Skills', help='Comma separated, used to recommend jobs.')
    aa_experience_years = fields.Integer('Years of Experience')
    aa_preferred_location = fields.Char('Preferred Location')
    aa_linkedin_url = fields.Char('LinkedIn Profile')
    aa_cv_attachment_id = fields.Many2one('ir.attachment', 'Résumé / CV', copy=False, ondelete='set null')
    aa_saved_job_ids = fields.One2many('aa.job.saved', 'partner_id', 'Saved Jobs')
    aa_saved_job_count = fields.Integer(compute='_compute_aa_saved_job_count')

    def _compute_aa_saved_job_count(self):
        data = self.env['aa.job.saved']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count'])
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.aa_saved_job_count = counts.get(partner.id, 0)

    # ------------------------------------------------------------------
    # Website welcome popup (once per signed-in session)
    # ------------------------------------------------------------------
    def _aajp_welcome_values(self):
        self.ensure_one()
        if not request or request.session.get('aajp_welcome_done'):
            return False
        request.session['aajp_welcome_done'] = True
        partner = self.sudo()
        env = partner.env
        applicants = env['hr.applicant'].sudo().with_context(active_test=False).search(
            [('partner_id', '=', partner.id)], order='create_date desc, id desc')
        ongoing = applicants.filtered(lambda a: a.application_status == 'ongoing')
        latest = applicants[:1]
        next_event = env['calendar.event'].sudo().search(
            [('applicant_id', 'in', applicants.ids), ('stop', '>=', fields.Datetime.now())],
            order='start asc', limit=1)
        tz = request.env.user.tz or 'UTC'
        latest_status = latest._aa_portal_status() if latest else False
        return {
            'first_name': (partner.name or '').split(' ')[0] or partner.name,
            'is_new': not applicants,
            'applied': len(applicants),
            'shortlisted': len(ongoing.filtered(lambda a: a.stage_id.aa_portal_shortlist)),
            'unread': env['aa.job.notification'].sudo().search_count(
                [('partner_id', '=', partner.id), ('is_read', '=', False)]),
            'latest_job': latest.job_id.name if latest else False,
            'latest_label': latest_status[0] if latest_status else False,
            'latest_tone': latest_status[1] if latest_status else False,
            'next_job': next_event.applicant_id.job_id.name or next_event.name if next_event else False,
            'next_when': format_datetime(env, next_event.start, tz=tz, dt_format='EEE d MMM · HH:mm')
                         if next_event and not next_event.allday else (_('All day') if next_event else False),
            'open_jobs': env['hr.job'].sudo().search_count([('website_published', '=', True)])
                         if env['hr.job']._fields['website_published'].store
                         else env['hr.job'].sudo().search_count([('is_published', '=', True)]),
        }

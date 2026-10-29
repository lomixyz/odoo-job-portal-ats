# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models, release
from odoo.exceptions import AccessError
from odoo.tools import format_date, format_datetime

RECRUITER_GROUP = 'hr_recruitment.group_hr_recruitment_user'
MANAGER_GROUP = 'hr_recruitment.group_hr_recruitment_manager'


class HrJob(models.Model):
    _inherit = 'hr.job'

    # ------------------------------------------------------------------
    # Version helpers
    # ------------------------------------------------------------------
    @api.model
    def _aa_pub_field(self):
        """Stored publish flag (website_published became computed after 17)."""
        return 'website_published' if self._fields['website_published'].store else 'is_published'

    def _aa_publish_vals(self, value):
        vals = {'website_published': value}
        if 'is_published' in self._fields:
            vals['is_published'] = value
        return vals

    @api.model
    def _aa_recruiter_field(self):
        for name in ('user_id', 'recruiter_id'):
            if name in self._fields:
                return name
        return False

    @api.model
    def _aa_employment_field(self):
        for name in ('contract_type_id', 'employee_type_id'):
            if name in self._fields:
                return name
        return False

    # ------------------------------------------------------------------
    # Filled positions
    # ------------------------------------------------------------------
    def _aa_hired_counts(self):
        data = self.env['hr.applicant'].sudo().with_context(active_test=False)._read_group(
            [('job_id', 'in', self.ids), ('date_closed', '!=', False)], ['job_id'], ['__count'])
        return {job.id: count for job, count in data if job}

    def _aa_filled_ids(self):
        """Jobs whose recruitment target is reached.

        Up to Odoo 17 "Target" is a fixed number compared with the hired applicants.
        From Odoo 18 "Target" counts down on every hire, so 0 after a hire means filled.
        A job with target 0 and nobody hired has no limit and stays open.
        """
        hired = self._aa_hired_counts()
        countdown = release.version_info[0] >= 18
        filled = set()
        for job in self:
            count = hired.get(job.id, 0)
            if countdown:
                if count and job.no_of_recruitment <= 0:
                    filled.add(job.id)
            elif job.no_of_recruitment > 0 and count >= job.no_of_recruitment:
                filled.add(job.id)
        return filled

    def _aa_is_filled(self):
        self.ensure_one()
        return self.id in self._aa_filled_ids()

    def _aa_open_positions(self):
        """Positions still to fill (0 when unknown or filled)."""
        self.ensure_one()
        if release.version_info[0] >= 18:
            return max(0, self.no_of_recruitment)
        return max(0, self.no_of_recruitment - self._aa_hired_counts().get(self.id, 0))

    def _aa_hire_limit(self):
        """Remaining hires allowed, or None when the position has no target."""
        self.ensure_one()
        hired = self._aa_hired_counts().get(self.id, 0)
        if release.version_info[0] >= 18:
            if self.no_of_recruitment <= 0 and not hired:
                return None
            return max(0, self.no_of_recruitment)
        if self.no_of_recruitment <= 0:
            return None
        return max(0, self.no_of_recruitment - hired)

    def _aa_total_target(self, hired_count):
        """Original target: on Odoo 18+ the field holds the remaining positions."""
        self.ensure_one()
        if release.version_info[0] >= 18:
            return self.no_of_recruitment + hired_count
        return self.no_of_recruitment

    @api.model
    def _aa_check_recruiter(self):
        if not self.env.user.has_group(RECRUITER_GROUP):
            raise AccessError(_('Only Recruitment officers and managers can use the recruitment dashboard.'))

    # ------------------------------------------------------------------
    # Dashboard data
    # ------------------------------------------------------------------
    @api.model
    def _aa_in_progress_domain(self):
        return [('stage_id.hired_stage', '=', False), ('date_closed', '=', False)]

    @api.model
    def _aa_count_by(self, model, domain, field):
        data = self.env[model]._read_group(domain, [field], ['__count'])
        return {rec.id: count for rec, count in data if rec}

    @api.model
    def aa_recruitment_dashboard_data(self):
        self._aa_check_recruiter()
        Applicant = self.env['hr.applicant']
        Event = self.env['calendar.event']
        now = fields.Datetime.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tz = self.env.user.tz or 'UTC'
        in_progress = self._aa_in_progress_domain()
        pub = self._aa_pub_field()
        recruiter_field = self._aa_recruiter_field()
        type_field = self._aa_employment_field()

        jobs = self.search([], order='%s desc, name asc' % pub)
        progress = self._aa_count_by('hr.applicant', [('job_id', 'in', jobs.ids)] + in_progress, 'job_id')
        new = self._aa_count_by('hr.applicant', [('job_id', 'in', jobs.ids), ('create_date', '>=', week_ago)], 'job_id')
        hired = jobs._aa_hired_counts()

        filled_ids = jobs._aa_filled_ids()
        job_rows = []
        for job in jobs:
            job_rows.append({
                'id': job.id,
                'name': job.name,
                'department': job.department_id.name or '',
                'company': job.company_id.name or '',
                'type': job[type_field].name if type_field and job[type_field] else '',
                'recruiter': job[recruiter_field].name if recruiter_field and job[recruiter_field] else '',
                'published': bool(job.website_published),
                'in_progress': progress.get(job.id, 0),
                'new': new.get(job.id, 0),
                'hired': hired.get(job.id, 0),
                'target': job._aa_total_target(hired.get(job.id, 0)),
                'filled': job.id in filled_ids,
            })

        # Pipeline funnel across all open positions
        stages = self.env['hr.recruitment.stage'].search([], order='sequence asc, id asc')
        per_stage = self._aa_count_by('hr.applicant', in_progress, 'stage_id')
        funnel_max = max(per_stage.values()) if per_stage else 0
        funnel = [{
            'id': stage.id,
            'name': stage.name,
            'count': per_stage.get(stage.id, 0),
            'pct': round(100.0 * per_stage.get(stage.id, 0) / funnel_max) if funnel_max else 0,
            'shortlist': bool(stage.aa_portal_shortlist),
        } for stage in stages if not stage.hired_stage]

        recent = Applicant.search([], order='create_date desc, id desc', limit=7)
        events = Event.search([('applicant_id', '!=', False), ('stop', '>=', now)], order='start asc', limit=6)

        def status(app):
            if app.date_closed or app.stage_id.hired_stage:
                return _('Hired'), 'success'
            return app.stage_id.name or _('New'), 'shortlist' if app.stage_id.aa_portal_shortlist else 'progress'

        recent_rows = []
        for app in recent:
            label, tone = status(app)
            name = app.partner_name or app.partner_id.name or app.display_name
            recent_rows.append({
                'id': app.id, 'name': name, 'initial': (name or '?')[:1].upper(),
                'job': app.job_id.name or _('No position'),
                'date': format_date(self.env, app.create_date),
                'status': label, 'tone': tone, 'portal': bool(app.aa_portal_applied),
                'ats': app.aa_ats_score if app.aa_ats_report_id else False,
                'ats_tone': {'excellent': 'success', 'good': 'progress', 'fair': 'shortlist', 'poor': 'danger'}.get(app.aa_ats_grade, 'progress'),
            })

        event_rows = []
        for ev in events:
            app = ev.applicant_id
            event_rows.append({
                'id': ev.id,
                'applicant_id': app.id,
                'name': app.partner_name or app.partner_id.name or ev.name,
                'job': app.job_id.name or ev.name,
                'month': format_datetime(self.env, ev.start, tz=tz, dt_format='MMM'),
                'day': format_datetime(self.env, ev.start, tz=tz, dt_format='d'),
                'time': _('All day') if ev.allday else format_datetime(self.env, ev.start, tz=tz, dt_format='EEE HH:mm'),
                'location': ev.location or '',
            })

        return {
            'is_manager': self.env.user.has_group(MANAGER_GROUP),
            'user_name': self.env.user.name,
            'kpis': {
                'published': self.search_count([(pub, '=', True)]),
                'in_progress': Applicant.search_count(in_progress),
                'new_week': Applicant.search_count([('create_date', '>=', week_ago)]),
                'interviews': Event.search_count([('applicant_id', '!=', False), ('stop', '>=', now)]),
                'hired_month': Applicant.search_count([('date_closed', '>=', month_start)]),
                'portal_month': Applicant.search_count([('aa_portal_applied', '=', True), ('create_date', '>=', month_ago)]),
                'all_month': Applicant.search_count([('create_date', '>=', month_ago)]),
            },
            'jobs': job_rows,
            'funnel': funnel,
            'recent': recent_rows,
            'interviews': event_rows,
        }

    # ------------------------------------------------------------------
    # Dashboard actions
    # ------------------------------------------------------------------
    def aa_dashboard_toggle_publish(self):
        self._aa_check_recruiter()
        for job in self:
            job.write(job._aa_publish_vals(not job.website_published))
        return True

    @api.model
    def _aa_list_type(self):
        return 'list' if release.version_info[0] >= 18 else 'tree'

    @api.model
    def aa_dashboard_action(self, kind, res_id=False):
        """Return a window action for a dashboard click."""
        self._aa_check_recruiter()
        now = fields.Datetime.now()
        lst = self._aa_list_type()
        applicant_views = [(False, 'kanban'), (False, lst), (False, 'form')]

        def applicants(name, domain, context=None, views=None):
            return {
                'type': 'ir.actions.act_window',
                'name': name,
                'res_model': 'hr.applicant',
                'views': views or [(False, lst), (False, 'kanban'), (False, 'form')],
                'domain': domain,
                'context': context or {},
                'target': 'current',
            }

        if kind == 'job_pipeline':
            job = self.browse(int(res_id)).exists()
            return applicants(job.name, [('job_id', '=', job.id)],
                              {'default_job_id': job.id, 'search_default_job_id': job.id,
                               'default_company_id': job.company_id.id},
                              views=applicant_views)
        if kind == 'job_form':
            return {'type': 'ir.actions.act_window', 'res_model': 'hr.job', 'res_id': int(res_id),
                    'views': [(False, 'form')], 'target': 'current', 'name': _('Job Position')}
        if kind == 'job_new':
            return {'type': 'ir.actions.act_window', 'res_model': 'hr.job', 'views': [(False, 'form')],
                    'target': 'current', 'name': _('New Job Position'),
                    'context': {'default_' + self._aa_publish_field_for_default(): False}}
        if kind == 'jobs':
            return {'type': 'ir.actions.act_window', 'res_model': 'hr.job', 'name': _('Job Positions'),
                    'views': [(False, lst), (False, 'form')], 'target': 'current'}
        if kind == 'applicant':
            return {'type': 'ir.actions.act_window', 'res_model': 'hr.applicant', 'res_id': int(res_id),
                    'views': [(False, 'form')], 'target': 'current', 'name': _('Applicant'),
                    'context': {'active_test': False}}
        if kind == 'event':
            return {'type': 'ir.actions.act_window', 'res_model': 'calendar.event', 'res_id': int(res_id),
                    'views': [(False, 'form')], 'target': 'current', 'name': _('Interview')}
        if kind == 'in_progress':
            return applicants(_('Applications in Progress'), self._aa_in_progress_domain(), views=applicant_views)
        if kind == 'stage':
            stage = self.env['hr.recruitment.stage'].browse(int(res_id)).exists()
            return applicants(stage.name, [('stage_id', '=', stage.id)] + self._aa_in_progress_domain())
        if kind == 'new_week':
            return applicants(_('New This Week'), [('create_date', '>=', now - timedelta(days=7))])
        if kind == 'hired_month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return applicants(_('Hired This Month'), [('date_closed', '>=', start)])
        if kind == 'portal':
            return applicants(_('Applied via Candidate Portal'), [('aa_portal_applied', '=', True)])
        if kind == 'all_applicants':
            return applicants(_('Applications'), [])
        if kind == 'interviews':
            return {'type': 'ir.actions.act_window', 'res_model': 'calendar.event', 'name': _('Interviews'),
                    'views': [(False, lst), (False, 'calendar'), (False, 'form')],
                    'domain': [('applicant_id', '!=', False), ('stop', '>=', now)], 'target': 'current'}
        return False

    @api.model
    def _aa_publish_field_for_default(self):
        return 'is_published' if 'is_published' in self._fields else 'website_published'

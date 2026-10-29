# -*- coding: utf-8 -*-
"""Recruiter side of the job portal.

Internal users with the Recruitment "Officer" right manage job positions and
applicants from a website dashboard at /recruiter. Everything runs with the
user's own access rights (no sudo), so record rules and multi-company apply.
"""
from datetime import datetime, timedelta

import pytz
from markupsafe import Markup
from werkzeug.exceptions import Forbidden, NotFound

from odoo import _, fields, http, release
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.tools import html2plaintext, plaintext2html

from odoo.addons.portal.controllers.portal import pager as portal_pager

from .main import ICONS, AaJobPortal, _icon

RECRUITER_GROUP = 'hr_recruitment.group_hr_recruitment_user'
PAGE_SIZE = 20

ICONS.update({
    'plus': '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    'edit': '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    'users': '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    'eye': '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    'eye-off': '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>'
               '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>'
               '<line x1="1" y1="1" x2="23" y2="23"/>',
    'layers': '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/>'
              '<polyline points="2 12 12 17 22 12"/>',
    'mail': '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>'
            '<polyline points="22,6 12,13 2,6"/>',
    'phone': '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 '
             '19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 '
             '2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
    'message': '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    'award': '<circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/>',
    'rotate': '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
    'slash': '<circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>',
    'app': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/>',
})


class AaJobPortalRecruiter(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def _h(self):
        """Formatting helpers shared with the candidate side."""
        return AaJobPortal()

    def _check_recruiter(self):
        if not request.env.user.has_group(RECRUITER_GROUP):
            raise Forbidden()

    def _now(self):
        return fields.Datetime.now()

    def _stages_for(self, job):
        domain = [('job_ids', '=', False)]
        if job:
            domain = ['|', ('job_ids', '=', False), ('job_ids', '=', job.id)]
        return request.env['hr.recruitment.stage'].search(domain, order='sequence asc, id asc')

    def _count_by_job(self, domain):
        data = request.env['hr.applicant']._read_group(domain, ['job_id'], ['__count'])
        return {job.id: count for job, count in data if job}

    def _employment_field(self):
        Job = request.env['hr.job']
        for name in ('contract_type_id', 'employee_type_id'):
            if name in Job._fields:
                return name
        return False

    def _pub_field(self):
        """Stored publish flag (website_published is computed in recent versions)."""
        Job = request.env['hr.job']
        return 'website_published' if Job._fields['website_published'].store else 'is_published'

    def _publish_vals(self, value):
        vals = {'website_published': value}
        if 'is_published' in request.env['hr.job']._fields:
            vals['is_published'] = value
        return vals

    def _recruiter_field(self):
        """hr.job recruiter: user_id (res.users) up to 17, recruiter_id (hr.employee) later."""
        Job = request.env['hr.job']
        for name in ('user_id', 'recruiter_id'):
            if name in Job._fields:
                return name
        return False

    def _recruiter_options(self):
        field = self._recruiter_field()
        if not field:
            return request.env['res.users']
        users = self._recruiter_users()
        comodel = request.env['hr.job']._fields[field].comodel_name
        if comodel == 'res.users':
            return users
        return request.env[comodel].search([('user_id', 'in', users.ids)], order='name')

    def _default_recruiter(self):
        field = self._recruiter_field()
        if not field:
            return False
        comodel = request.env['hr.job']._fields[field].comodel_name
        if comodel == 'res.users':
            return request.env.user.id
        return request.env.user.employee_id.id if 'employee_id' in request.env.user._fields else False

    def _recruiter_name(self, job):
        field = self._recruiter_field()
        return job[field].name if field and job[field] else False

    def _recruiter_users(self):
        group = request.env.ref(RECRUITER_GROUP).sudo()
        for name in ('all_user_ids', 'user_ids', 'users'):
            if name in group._fields:
                return group[name].filtered(lambda u: not u.share and u.active).sorted('name')
        return request.env['res.users']

    def _notes_html(self, applicant):
        for name in ('description', 'applicant_notes'):
            if name in applicant._fields and applicant[name]:
                return applicant[name]
        return False

    def _applicant_name(self, applicant):
        return applicant.partner_name or applicant.partner_id.name or applicant.display_name

    def _status(self, applicant):
        """(label, tone) for recruiters — internal stage names are fine here."""
        if not applicant.active:
            return (_('Refused') if applicant.refuse_reason_id else _('Archived')), 'danger'
        if applicant.date_closed or applicant.stage_id.hired_stage:
            return _('Hired'), 'success'
        tone = 'shortlist' if applicant.stage_id.aa_portal_shortlist else 'progress'
        return applicant.stage_id.name or _('New'), tone

    def _parse_local_dt(self, value):
        """datetime-local input (user's timezone) -> naive UTC datetime."""
        local = datetime.strptime(value, '%Y-%m-%dT%H:%M')
        return self._h._user_tz().localize(local).astimezone(pytz.utc).replace(tzinfo=None)

    def _safe_next(self, url, default):
        if url and url.startswith('/recruiter') and '//' not in url:
            return url
        return default

    def _backend_url(self, model, res_id):
        if release.version_info[0] >= 18:
            return '/odoo/%s/%s' % (model, res_id)
        return '/web#model=%s&id=%s&view_type=form' % (model, res_id)

    def _app_url(self):
        if release.version_info[0] >= 18:
            return '/odoo/recruitment'
        menu = request.env.ref('hr_recruitment.menu_hr_recruitment_root', raise_if_not_found=False)
        return '/web#menu_id=%s' % menu.id if menu else '/web'

    def _values(self, active, extra=None):
        user = request.env.user
        h = self._h
        values = {
            'aajr_user': user,
            'aajr_active': active,
            'aajr_is_manager': user.has_group('hr_recruitment.group_hr_recruitment_manager'),
            'aajr_upcoming_count': request.env['calendar.event'].search_count(
                [('applicant_id', '!=', False), ('start', '>=', self._now())]),
            'icon': _icon,
            'fmt_dt': h._fmt_dt,
            'fmt_d': h._fmt_d,
            'job_location': h._job_location,
            'company_initial': h._company_initial,
            'employment_type': h._employment_type,
            'applicant_name': self._applicant_name,
            'r_status': self._status,
            'backend_url': self._backend_url,
            'recruiter_name': self._recruiter_name,
            'aajr_app_url': self._app_url(),
        }
        values.update(extra or {})
        return values

    def _render(self, template, active, extra=None):
        return request.render(template, self._values(active, extra))

    def _get(self, model, rec_id, active_test=True):
        record = request.env[model].with_context(active_test=active_test).browse(int(rec_id)).exists()
        if not record:
            raise NotFound()
        try:
            record.check_access('read') if hasattr(record, 'check_access') else record.check_access_rule('read')
        except AccessError:
            raise NotFound()
        return record

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @http.route(['/recruiter', '/recruiter/dashboard'], type='http', auth='user', website=True)
    def aajr_dashboard(self, **kw):
        self._check_recruiter()
        Applicant = request.env['hr.applicant']
        Job = request.env['hr.job']
        now = self._now()
        week_ago = now - timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        in_progress = [('stage_id.hired_stage', '=', False), ('date_closed', '=', False)]

        jobs = Job.search([], order='%s desc, name asc' % self._pub_field(), limit=12)
        values = {
            'stat_open': Job.search_count([(self._pub_field(), '=', True)]),
            'stat_progress': Applicant.search_count(in_progress),
            'stat_new': Applicant.search_count([('create_date', '>=', week_ago)]),
            'stat_hired': Applicant.search_count([('date_closed', '>=', month_start)]),
            'jobs': jobs,
            'job_progress': self._count_by_job([('job_id', 'in', jobs.ids)] + in_progress),
            'job_new': self._count_by_job([('job_id', 'in', jobs.ids), ('create_date', '>=', week_ago)]),
            'job_hired': self._count_by_job([('job_id', 'in', jobs.ids), ('date_closed', '!=', False)]),
            'recent': Applicant.search([], order='create_date desc, id desc', limit=6),
            'interviews': request.env['calendar.event'].search(
                [('applicant_id', '!=', False), ('stop', '>=', now)], order='start asc', limit=5),
            'page_title': _('Recruiter Dashboard'),
        }
        return self._render('aa_job_portal.r_page_dashboard', 'dashboard', values)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------
    @http.route('/recruiter/jobs', type='http', auth='user', website=True)
    def aajr_jobs(self, filter='all', search='', **kw):
        self._check_recruiter()
        Job = request.env['hr.job'].with_context(active_test=False)
        pub = self._pub_field()
        filters = {
            'all': [('active', '=', True)],
            'published': [('active', '=', True), (pub, '=', True)],
            'unpublished': [('active', '=', True), (pub, '=', False)],
            'archived': [('active', '=', False)],
        }
        filter = filter if filter in filters else 'all'
        domain = list(filters[filter])
        search = (search or '').strip()
        if search:
            domain += ['|', ('name', 'ilike', search), ('department_id.name', 'ilike', search)]
        jobs = Job.search(domain, order='%s desc, name asc' % pub)
        in_progress = [('job_id', 'in', jobs.ids), ('stage_id.hired_stage', '=', False), ('date_closed', '=', False)]
        return self._render('aa_job_portal.r_page_jobs', 'jobs', {
            'jobs': jobs,
            'filter': filter,
            'search': search,
            'counts': {k: Job.search_count(d) for k, d in filters.items()},
            'job_progress': self._count_by_job(in_progress),
            'job_new': self._count_by_job([('job_id', 'in', jobs.ids),
                                           ('create_date', '>=', self._now() - timedelta(days=7))]),
            'saved': kw.get('saved'),
            'page_title': _('Job Positions'),
        })

    def _job_form_values(self, job, error=False, post=None):
        type_field = self._employment_field()
        post = post or {}
        description = post.get('description')
        if description is None:
            description = html2plaintext(job.description or '').strip() if job else ''
        return {
            'job': job,
            'error': error,
            'departments': request.env['hr.department'].search([], order='name'),
            'recruiters': self._recruiter_options(),
            'recruiter_field': self._recruiter_field(),
            'type_field': type_field,
            'types': request.env[request.env['hr.job']._fields[type_field].comodel_name].search([]) if type_field else [],
            'form': {
                'name': post.get('name', job.name if job else ''),
                'department_id': int(post.get('department_id') or (job.department_id.id if job else 0) or 0),
                'type_id': int(post.get('type_id') or (job[type_field].id if job and type_field else 0) or 0),
                'user_id': int(post.get('user_id') or (job[self._recruiter_field()].id if job and self._recruiter_field()
                                                        else self._default_recruiter()) or 0),
                'no_of_recruitment': post.get('no_of_recruitment', job.no_of_recruitment if job else 1),
                'description': description,
                'published': bool(post.get('published')) if post else bool(job and job.website_published),
            },
            'page_title': job.name if job else _('New Job Position'),
        }

    @http.route(['/recruiter/jobs/new', '/recruiter/jobs/<int:job_id>/edit'], type='http', auth='user', website=True)
    def aajr_job_form(self, job_id=None, **kw):
        self._check_recruiter()
        job = self._get('hr.job', job_id, active_test=False) if job_id else request.env['hr.job']
        return self._render('aa_job_portal.r_page_job_form', 'jobs', self._job_form_values(job))

    @http.route('/recruiter/jobs/save', type='http', auth='user', website=True, methods=['POST'])
    def aajr_job_save(self, job_id=None, **post):
        self._check_recruiter()
        job = self._get('hr.job', job_id, active_test=False) if job_id else request.env['hr.job']
        name = (post.get('name') or '').strip()
        if not name:
            return self._render('aa_job_portal.r_page_job_form', 'jobs',
                                self._job_form_values(job, _('The job title is required.'), post))
        try:
            target = max(0, int(post.get('no_of_recruitment') or 0))
        except ValueError:
            target = 0
        vals = {
            'name': name,
            'department_id': int(post.get('department_id') or 0) or False,
            'no_of_recruitment': target,
        }
        vals.update(self._publish_vals(bool(post.get('published'))))
        recruiter_field = self._recruiter_field()
        if recruiter_field:
            vals[recruiter_field] = int(post.get('user_id') or 0) or False
        type_field = self._employment_field()
        if type_field:
            vals[type_field] = int(post.get('type_id') or 0) or False
        text = (post.get('description') or '').strip()
        if not job or text != html2plaintext(job.description or '').strip():
            vals['description'] = plaintext2html(text) if text else False
        try:
            if job:
                job.write(vals)
            else:
                job = request.env['hr.job'].create(vals)
        except (AccessError, UserError, ValidationError) as e:
            return self._render('aa_job_portal.r_page_job_form', 'jobs',
                                self._job_form_values(job, str(e), post))
        return request.redirect('/recruiter/jobs/%s?saved=1' % job.id)

    @http.route('/recruiter/jobs/<int:job_id>/publish', type='http', auth='user', website=True, methods=['POST'])
    def aajr_job_publish(self, job_id, next=None, **kw):
        self._check_recruiter()
        job = self._get('hr.job', job_id)
        job.write(self._publish_vals(not job.website_published))
        return request.redirect(self._safe_next(next, '/recruiter/jobs'))

    @http.route('/recruiter/jobs/<int:job_id>/archive', type='http', auth='user', website=True, methods=['POST'])
    def aajr_job_archive(self, job_id, **kw):
        self._check_recruiter()
        job = self._get('hr.job', job_id, active_test=False)
        if job.active:
            job.action_archive()
        else:
            job.action_unarchive()
        return request.redirect('/recruiter/jobs?filter=%s' % ('archived' if not job.active else 'all'))

    @http.route('/recruiter/jobs/<int:job_id>', type='http', auth='user', website=True)
    def aajr_job_pipeline(self, job_id, **kw):
        self._check_recruiter()
        job = self._get('hr.job', job_id, active_test=False)
        stages = self._stages_for(job)
        applicants = request.env['hr.applicant'].search([('job_id', '=', job.id)], order='create_date desc')
        refused = request.env['hr.applicant'].with_context(active_test=False).search(
            [('job_id', '=', job.id), ('active', '=', False)], order='write_date desc', limit=30)
        columns = [(stage, applicants.filtered(lambda a, s=stage: a.stage_id == s)) for stage in stages]
        orphan = applicants.filtered(lambda a: a.stage_id not in stages)
        if orphan:
            columns.append((request.env['hr.recruitment.stage'], orphan))
        return self._render('aa_job_portal.r_page_pipeline', 'jobs', {
            'job': job, 'columns': columns, 'stages': stages, 'refused': refused,
            'total': len(applicants), 'saved': kw.get('saved'), 'page_title': job.name,
        })

    # ------------------------------------------------------------------
    # Applications
    # ------------------------------------------------------------------
    @http.route(['/recruiter/applications', '/recruiter/applications/page/<int:page>'],
                type='http', auth='user', website=True)
    def aajr_applications(self, page=1, status='progress', job='', search='', **kw):
        self._check_recruiter()
        Applicant = request.env['hr.applicant'].with_context(active_test=False)
        week_ago = self._now() - timedelta(days=7)
        filters = {
            'progress': [('active', '=', True), ('stage_id.hired_stage', '=', False), ('date_closed', '=', False)],
            'new': [('active', '=', True), ('create_date', '>=', week_ago)],
            'hired': [('date_closed', '!=', False)],
            'refused': [('active', '=', False)],
            'all': ['|', ('active', '=', True), ('active', '=', False)],
        }
        status = status if status in filters else 'progress'
        domain = list(filters[status])
        job_id = int(job) if str(job).isdigit() else 0
        if job_id:
            domain.append(('job_id', '=', job_id))
        search = (search or '').strip()
        if search:
            domain += ['|', '|', ('partner_name', 'ilike', search), ('email_from', 'ilike', search),
                       ('job_id.name', 'ilike', search)]
        total = Applicant.search_count(domain)
        url_args = {k: v for k, v in (('status', status), ('job', job_id or ''), ('search', search)) if v}
        pager = portal_pager(url='/recruiter/applications', total=total, page=page, step=PAGE_SIZE, url_args=url_args)
        applicants = Applicant.search(domain, order='create_date desc, id desc', limit=PAGE_SIZE, offset=pager['offset'])
        return self._render('aa_job_portal.r_page_applications', 'applications', {
            'applicants': applicants, 'pager': pager, 'status': status, 'job_id': job_id, 'search': search,
            'total': total, 'jobs': request.env['hr.job'].search([], order='name'),
            'counts': {k: Applicant.search_count(d + ([('job_id', '=', job_id)] if job_id else []))
                       for k, d in filters.items()},
            'page_title': _('Applications'),
        })

    @http.route('/recruiter/applicant/<int:applicant_id>', type='http', auth='user', website=True)
    def aajr_applicant(self, applicant_id, **kw):
        self._check_recruiter()
        applicant = self._get('hr.applicant', applicant_id, active_test=False)
        messages = applicant.message_ids.filtered(
            lambda m: m.message_type in ('comment', 'email') and html2plaintext(m.body or '').strip())[:15]
        attachments = request.env['ir.attachment'].search(
            [('res_model', '=', 'hr.applicant'), ('res_id', '=', applicant.id)], order='create_date desc')
        default_start = (self._h._to_local(self._now()) + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0)
        return self._render('aa_job_portal.r_page_applicant', 'applications', {
            'applicant': applicant,
            'stages': self._stages_for(applicant.job_id),
            'reasons': request.env['hr.applicant.refuse.reason'].search([]),
            'notes_html': self._notes_html(applicant),
            'messages': messages,
            'attachments': attachments,
            'meetings': request.env['calendar.event'].search([('applicant_id', '=', applicant.id)], order='start desc'),
            'default_start': default_start.strftime('%Y-%m-%dT%H:%M'),
            'flash': kw.get('done'),
            'error': kw.get('error'),
            'page_title': self._applicant_name(applicant),
        })

    def _back(self, applicant, next_url=None, done=None):
        default = '/recruiter/applicant/%s' % applicant.id + ('?done=%s' % done if done else '')
        return request.redirect(self._safe_next(next_url, default))

    @http.route('/recruiter/applicant/<int:applicant_id>/stage', type='http', auth='user', website=True, methods=['POST'])
    def aajr_applicant_stage(self, applicant_id, stage_id=None, next=None, **kw):
        self._check_recruiter()
        applicant = self._get('hr.applicant', applicant_id)
        stage = request.env['hr.recruitment.stage'].browse(int(stage_id or 0)).exists()
        if stage and stage != applicant.stage_id:
            applicant.write({'stage_id': stage.id})
        return self._back(applicant, next, 'stage')

    @http.route('/recruiter/applicant/<int:applicant_id>/refuse', type='http', auth='user', website=True, methods=['POST'])
    def aajr_applicant_refuse(self, applicant_id, reason_id=None, **kw):
        self._check_recruiter()
        applicant = self._get('hr.applicant', applicant_id)
        vals = {'refuse_reason_id': int(reason_id or 0) or False}
        if 'refuse_date' in applicant._fields:
            vals['refuse_date'] = self._now()
        applicant.write(vals)
        applicant.action_archive()
        return self._back(applicant, None, 'refused')

    @http.route('/recruiter/applicant/<int:applicant_id>/restore', type='http', auth='user', website=True, methods=['POST'])
    def aajr_applicant_restore(self, applicant_id, **kw):
        self._check_recruiter()
        applicant = self._get('hr.applicant', applicant_id, active_test=False)
        applicant.action_unarchive()
        applicant.reset_applicant()
        return self._back(applicant, None, 'restored')

    @http.route('/recruiter/applicant/<int:applicant_id>/note', type='http', auth='user', website=True, methods=['POST'])
    def aajr_applicant_note(self, applicant_id, note='', **kw):
        self._check_recruiter()
        applicant = self._get('hr.applicant', applicant_id, active_test=False)
        note = (note or '').strip()
        if note:
            applicant.message_post(body=plaintext2html(note), message_type='comment', subtype_xmlid='mail.mt_note')
        return self._back(applicant, None, 'note')

    @http.route('/recruiter/applicant/<int:applicant_id>/interview', type='http', auth='user', website=True, methods=['POST'])
    def aajr_applicant_interview(self, applicant_id, start='', duration='1', location='', title='', **kw):
        self._check_recruiter()
        applicant = self._get('hr.applicant', applicant_id)
        try:
            start_utc = self._parse_local_dt(start)
            hours = max(0.25, min(12.0, float(duration or 1)))
        except ValueError:
            return request.redirect('/recruiter/applicant/%s?error=date' % applicant.id)
        partners = request.env.user.partner_id | applicant.partner_id
        name = (title or '').strip() or _('Interview: %s', applicant.job_id.name or self._applicant_name(applicant))
        request.env['calendar.event'].create({
            'name': name,
            'applicant_id': applicant.id,
            'start': start_utc,
            'stop': start_utc + timedelta(hours=hours),
            'location': (location or '').strip() or False,
            'user_id': request.env.user.id,
            'partner_ids': [(6, 0, partners.ids)],
        })
        return self._back(applicant, None, 'interview')

    # ------------------------------------------------------------------
    # Interviews
    # ------------------------------------------------------------------
    @http.route('/recruiter/interviews', type='http', auth='user', website=True)
    def aajr_interviews(self, **kw):
        self._check_recruiter()
        Event = request.env['calendar.event']
        now = self._now()
        return self._render('aa_job_portal.r_page_interviews', 'interviews', {
            'upcoming': Event.search([('applicant_id', '!=', False), ('stop', '>=', now)], order='start asc', limit=100),
            'past': Event.search([('applicant_id', '!=', False), ('stop', '<', now)], order='start desc', limit=30),
            'page_title': _('Interviews'),
        })

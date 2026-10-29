# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Enable free sign-up on websites and flag interview / proposal stages as 'shortlisted'."""
    if 'auth_signup_uninvited' in env['website']._fields:
        env['website'].search([]).write({'auth_signup_uninvited': 'b2c'})
    for xmlid in ('hr_recruitment.stage_job2', 'hr_recruitment.stage_job3', 'hr_recruitment.stage_job4'):
        stage = env.ref(xmlid, raise_if_not_found=False)
        if stage:
            stage.aa_portal_shortlist = True

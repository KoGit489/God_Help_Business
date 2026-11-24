BEGIN;

CREATE SCHEMA IF NOT EXISTS casai_security;
REVOKE ALL ON SCHEMA casai_security FROM PUBLIC;

CREATE OR REPLACE FUNCTION casai_security.can_read_shared_project(project_key text, share_secret text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.share_links
        WHERE project_id = project_key AND token = share_secret
          AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP
    )
$$;
REVOKE ALL ON FUNCTION casai_security.can_read_shared_project(text, text) FROM PUBLIC;

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects FORCE ROW LEVEL SECURITY;
ALTER TABLE public.pins ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pins FORCE ROW LEVEL SECURITY;
ALTER TABLE public.annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.annotations FORCE ROW LEVEL SECURITY;
ALTER TABLE public.share_links ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS casai_owner ON public.projects;
CREATE POLICY casai_owner ON public.projects FOR ALL
    USING (owner_id = current_setting('casai.user_id', true))
    WITH CHECK (owner_id = current_setting('casai.user_id', true));
DROP POLICY IF EXISTS casai_shared_read ON public.projects;
CREATE POLICY casai_shared_read ON public.projects FOR SELECT
    USING (casai_security.can_read_shared_project(id, current_setting('casai.share_token', true)));

DROP POLICY IF EXISTS casai_owner ON public.pins;
CREATE POLICY casai_owner ON public.pins FOR ALL
    USING (EXISTS (SELECT 1 FROM public.projects WHERE id = pins.project_id AND owner_id = current_setting('casai.user_id', true)))
    WITH CHECK (EXISTS (SELECT 1 FROM public.projects WHERE id = pins.project_id AND owner_id = current_setting('casai.user_id', true)));
DROP POLICY IF EXISTS casai_shared_read ON public.pins;
CREATE POLICY casai_shared_read ON public.pins FOR SELECT
    USING (casai_security.can_read_shared_project(project_id, current_setting('casai.share_token', true)));

DROP POLICY IF EXISTS casai_owner ON public.annotations;
CREATE POLICY casai_owner ON public.annotations FOR ALL
    USING (EXISTS (SELECT 1 FROM public.projects WHERE id = annotations.project_id AND owner_id = current_setting('casai.user_id', true)))
    WITH CHECK (EXISTS (SELECT 1 FROM public.projects WHERE id = annotations.project_id AND owner_id = current_setting('casai.user_id', true)));
DROP POLICY IF EXISTS casai_shared_read ON public.annotations;
CREATE POLICY casai_shared_read ON public.annotations FOR SELECT
    USING (casai_security.can_read_shared_project(project_id, current_setting('casai.share_token', true)));

DROP POLICY IF EXISTS casai_owner ON public.share_links;
CREATE POLICY casai_owner ON public.share_links FOR ALL
    USING (EXISTS (SELECT 1 FROM public.projects WHERE id = share_links.project_id AND owner_id = current_setting('casai.user_id', true)))
    WITH CHECK (EXISTS (SELECT 1 FROM public.projects WHERE id = share_links.project_id AND owner_id = current_setting('casai.user_id', true)));
DROP POLICY IF EXISTS casai_shared_read ON public.share_links;
CREATE POLICY casai_shared_read ON public.share_links FOR SELECT
    USING (token = current_setting('casai.share_token', true) AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP);

COMMIT;
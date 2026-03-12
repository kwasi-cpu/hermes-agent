create schema if not exists app;

create or replace function app.set_request_context(
  p_tenant_id uuid,
  p_user_id uuid,
  p_role text
) returns void
language plpgsql
as $$
begin
  perform set_config('app.tenant_id', p_tenant_id::text, true);
  perform set_config('app.user_id', p_user_id::text, true);
  perform set_config('app.role', coalesce(p_role, ''), true);
end;
$$;

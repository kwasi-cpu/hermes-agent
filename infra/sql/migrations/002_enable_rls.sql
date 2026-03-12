-- Expected per-request transaction settings:
--   set local app.tenant_id = '<tenant-uuid>';
--   set local app.user_id = '<user-uuid>';
--   set local app.role = '<owner|admin|member|viewer>';

alter table tenant_users enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;
alter table memories enable row level security;
alter table tasks enable row level security;

alter table tenant_users force row level security;
alter table conversations force row level security;
alter table messages force row level security;
alter table memories force row level security;
alter table tasks force row level security;

drop policy if exists tenant_users_isolation on tenant_users;
create policy tenant_users_isolation on tenant_users
  using (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and (
      user_id = nullif(current_setting('app.user_id', true), '')::uuid
      or nullif(current_setting('app.role', true), '') in ('owner', 'admin')
    )
  )
  with check (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and nullif(current_setting('app.role', true), '') in ('owner', 'admin')
  );

drop policy if exists conversations_isolation on conversations;
create policy conversations_isolation on conversations
  using (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and (
      user_id = nullif(current_setting('app.user_id', true), '')::uuid
      or nullif(current_setting('app.role', true), '') in ('owner', 'admin')
    )
  )
  with check (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and (
      user_id = nullif(current_setting('app.user_id', true), '')::uuid
      or nullif(current_setting('app.role', true), '') in ('owner', 'admin')
    )
  );

drop policy if exists messages_isolation on messages;
create policy messages_isolation on messages
  using (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and (
      conversation_id in (
        select c.id from conversations c
        where c.tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
        and (
          c.user_id = nullif(current_setting('app.user_id', true), '')::uuid
          or nullif(current_setting('app.role', true), '') in ('owner', 'admin')
        )
      )
    )
  )
  with check (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
  );

drop policy if exists memories_isolation on memories;
create policy memories_isolation on memories
  using (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and user_id = nullif(current_setting('app.user_id', true), '')::uuid
  )
  with check (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and user_id = nullif(current_setting('app.user_id', true), '')::uuid
  );

drop policy if exists tasks_isolation on tasks;
create policy tasks_isolation on tasks
  using (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and (
      created_by = nullif(current_setting('app.user_id', true), '')::uuid
      or nullif(current_setting('app.role', true), '') in ('owner', 'admin')
    )
  )
  with check (
    tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
    and (
      created_by = nullif(current_setting('app.user_id', true), '')::uuid
      or nullif(current_setting('app.role', true), '') in ('owner', 'admin')
    )
  );

-- Run once in your Supabase SQL Editor. No public bucket and no anonymous table access.
create table if not exists public.ecoscope_runs (
  id uuid primary key,
  owner text not null,
  version integer not null default 0,
  snapshot text not null,
  summary jsonb not null default '{}'::jsonb,
  lock_token text,
  lock_until timestamptz not null default '-infinity',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists ecoscope_runs_owner_idx on public.ecoscope_runs(owner,created_at desc);
alter table public.ecoscope_runs enable row level security;
revoke all on public.ecoscope_runs from anon, authenticated;
grant all on public.ecoscope_runs to service_role;

create or replace function public.ecoscope_claim(p_id uuid,p_owner text,p_version integer,p_token text)
returns setof public.ecoscope_runs language sql security invoker set search_path=public as $$
 update public.ecoscope_runs set lock_token=p_token,lock_until=now()+interval '6 minutes'
 where id=p_id and owner=p_owner and version=p_version and lock_until<now() returning *;
$$;
create or replace function public.ecoscope_commit(p_id uuid,p_owner text,p_token text,p_snapshot text,p_summary jsonb)
returns setof public.ecoscope_runs language sql security invoker set search_path=public as $$
 update public.ecoscope_runs set snapshot=p_snapshot,summary=p_summary,version=version+1,
 lock_token=null,lock_until='-infinity',updated_at=now()
 where id=p_id and owner=p_owner and lock_token=p_token and lock_until>now() returning *;
$$;
create or replace function public.ecoscope_release(p_id uuid,p_owner text,p_token text)
returns void language sql security invoker set search_path=public as $$
 update public.ecoscope_runs set lock_token=null,lock_until='-infinity'
 where id=p_id and owner=p_owner and lock_token=p_token;
$$;
revoke all on function public.ecoscope_claim(uuid,text,integer,text) from public,anon,authenticated;
revoke all on function public.ecoscope_commit(uuid,text,text,text,jsonb) from public,anon,authenticated;
revoke all on function public.ecoscope_release(uuid,text,text) from public,anon,authenticated;
grant execute on function public.ecoscope_claim(uuid,text,integer,text) to service_role;
grant execute on function public.ecoscope_commit(uuid,text,text,text,jsonb) to service_role;
grant execute on function public.ecoscope_release(uuid,text,text) to service_role;

insert into storage.buckets(id,name,public,file_size_limit)
values('ecoscope-private','ecoscope-private',false,50000000)
on conflict(id) do update set public=false;

-- A shared gate respects Nominatim's one-request-per-second application limit.
create table if not exists public.ecoscope_limits(key text primary key, next_at timestamptz not null);
insert into public.ecoscope_limits values('geocode','-infinity') on conflict do nothing;
alter table public.ecoscope_limits enable row level security;
revoke all on public.ecoscope_limits from anon,authenticated;
grant all on public.ecoscope_limits to service_role;
create or replace function public.ecoscope_geocode_gate() returns boolean
language sql security invoker set search_path=public as $$
 with claimed as (update public.ecoscope_limits set next_at=now()+interval '1.2 seconds'
 where key='geocode' and next_at<now() returning key) select exists(select 1 from claimed);
$$;
revoke all on function public.ecoscope_geocode_gate() from public,anon,authenticated;
grant execute on function public.ecoscope_geocode_gate() to service_role;

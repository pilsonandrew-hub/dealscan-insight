create table if not exists public.pricing_recovery_requests (
  id uuid primary key default gen_random_uuid(),
  group_key text not null unique,
  year integer not null,
  make text not null,
  model text not null,
  state text,
  source_families text[] not null default '{}',
  candidate_count integer not null default 0 check (candidate_count >= 0),
  status text not null,
  recommended_action text not null,
  queue_status text not null default 'open',
  owner text,
  priority integer not null default 0,
  blocked_reason text,
  resolution_notes text,
  market_prices_usable integer not null default 0 check (market_prices_usable >= 0),
  market_prices_total integer not null default 0 check (market_prices_total >= 0),
  dealer_sales_usable integer not null default 0 check (dealer_sales_usable >= 0),
  dealer_sales_total integer not null default 0 check (dealer_sales_total >= 0),
  competitor_sales_usable integer not null default 0 check (competitor_sales_usable >= 0),
  competitor_sales_total integer not null default 0 check (competitor_sales_total >= 0),
  internal_history_usable integer not null default 0 check (internal_history_usable >= 0),
  internal_history_total integer not null default 0 check (internal_history_total >= 0),
  latest_proof_run_id text,
  latest_proof_head_sha text,
  last_seen_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  resolved_at timestamptz,
  check (queue_status in ('open','evidence_requested','evidence_received','preview_ready','applied','blocked','dismissed')),
  check (status in ('covered_by_market_prices','covered_by_dealer_sales','covered_by_competitor_sales','seedable_from_internal_history','insufficient_dealer_sales','insufficient_internal_history','insufficient_competitor_sales','blocked_no_internal_comp_evidence','dirty_source_row','expired_pricing_gap')),
  check (recommended_action in ('none','refresh_market_prices_from_dealer_sales','refresh_market_prices_from_competitor_sales','review_internal_history_for_completed_sales_evidence','request_completed_sales_evidence','wait_for_more_internal_history','ignore_dirty_source_row','ignore_expired_listing'))
);

create table if not exists public.pricing_recovery_request_events (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.pricing_recovery_requests(id) on delete cascade,
  event_type text not null,
  previous_queue_status text,
  next_queue_status text,
  actor text,
  reason text,
  proof_run_id text,
  head_sha text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_pricing_recovery_requests_queue_status
  on public.pricing_recovery_requests(queue_status);

create index if not exists idx_pricing_recovery_requests_status
  on public.pricing_recovery_requests(status);

create index if not exists idx_pricing_recovery_request_events_request_id
  on public.pricing_recovery_request_events(request_id);

alter table public.pricing_recovery_requests enable row level security;
alter table public.pricing_recovery_request_events enable row level security;

drop policy if exists service_role_all_pricing_recovery_requests
  on public.pricing_recovery_requests;

create policy service_role_all_pricing_recovery_requests
  on public.pricing_recovery_requests
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists service_role_all_pricing_recovery_request_events
  on public.pricing_recovery_request_events;

create policy service_role_all_pricing_recovery_request_events
  on public.pricing_recovery_request_events
  for all
  to service_role
  using (true)
  with check (true);

create or replace function public.set_pricing_recovery_requests_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists trg_pricing_recovery_requests_updated_at
  on public.pricing_recovery_requests;

create trigger trg_pricing_recovery_requests_updated_at
  before update on public.pricing_recovery_requests
  for each row
  execute function public.set_pricing_recovery_requests_updated_at();

create or replace function public.get_pricing_recovery_request_by_group_key(
  request_group_key text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  saved_request jsonb;
begin
  if auth.role() <> 'service_role' then
    raise exception 'get_pricing_recovery_request_by_group_key requires service_role'
      using errcode = '42501';
  end if;

  select jsonb_build_object(
    'id', request_rows.id,
    'group_key', request_rows.group_key,
    'queue_status', request_rows.queue_status,
    'owner', request_rows.owner,
    'priority', request_rows.priority,
    'blocked_reason', request_rows.blocked_reason,
    'resolution_notes', request_rows.resolution_notes,
    'resolved_at', request_rows.resolved_at
  )
  into saved_request
  from public.pricing_recovery_requests request_rows
  where request_rows.group_key = request_group_key
  limit 1;

  if not found then
    return null;
  end if;

  return saved_request;
end;
$$;

create or replace function public.sync_pricing_recovery_request(
  request_payload jsonb,
  event_payload jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  saved_request public.pricing_recovery_requests%rowtype;
begin
  if auth.role() <> 'service_role' then
    raise exception 'sync_pricing_recovery_request requires service_role'
      using errcode = '42501';
  end if;

  insert into public.pricing_recovery_requests (
    group_key,
    year,
    make,
    model,
    state,
    source_families,
    candidate_count,
    status,
    recommended_action,
    queue_status,
    owner,
    priority,
    blocked_reason,
    resolution_notes,
    market_prices_usable,
    market_prices_total,
    dealer_sales_usable,
    dealer_sales_total,
    competitor_sales_usable,
    competitor_sales_total,
    internal_history_usable,
    internal_history_total,
    latest_proof_run_id,
    latest_proof_head_sha,
    last_seen_at,
    resolved_at
  )
  values (
    request_payload->>'group_key',
    (request_payload->>'year')::integer,
    request_payload->>'make',
    request_payload->>'model',
    nullif(request_payload->>'state', ''),
    coalesce(array(select jsonb_array_elements_text(coalesce(request_payload->'source_families', '[]'::jsonb))), '{}'::text[]),
    coalesce((request_payload->>'candidate_count')::integer, 0),
    request_payload->>'status',
    request_payload->>'recommended_action',
    coalesce(nullif(request_payload->>'queue_status', ''), 'open'),
    nullif(request_payload->>'owner', ''),
    coalesce((request_payload->>'priority')::integer, 0),
    nullif(request_payload->>'blocked_reason', ''),
    nullif(request_payload->>'resolution_notes', ''),
    coalesce((request_payload->>'market_prices_usable')::integer, 0),
    coalesce((request_payload->>'market_prices_total')::integer, 0),
    coalesce((request_payload->>'dealer_sales_usable')::integer, 0),
    coalesce((request_payload->>'dealer_sales_total')::integer, 0),
    coalesce((request_payload->>'competitor_sales_usable')::integer, 0),
    coalesce((request_payload->>'competitor_sales_total')::integer, 0),
    coalesce((request_payload->>'internal_history_usable')::integer, 0),
    coalesce((request_payload->>'internal_history_total')::integer, 0),
    nullif(request_payload->>'latest_proof_run_id', ''),
    nullif(request_payload->>'latest_proof_head_sha', ''),
    coalesce(nullif(request_payload->>'last_seen_at', '')::timestamptz, timezone('utc', now())),
    nullif(request_payload->>'resolved_at', '')::timestamptz
  )
  on conflict (group_key) do update set
    year = excluded.year,
    make = excluded.make,
    model = excluded.model,
    state = excluded.state,
    source_families = excluded.source_families,
    candidate_count = excluded.candidate_count,
    status = excluded.status,
    recommended_action = excluded.recommended_action,
    queue_status = excluded.queue_status,
    owner = excluded.owner,
    priority = excluded.priority,
    blocked_reason = excluded.blocked_reason,
    resolution_notes = excluded.resolution_notes,
    market_prices_usable = excluded.market_prices_usable,
    market_prices_total = excluded.market_prices_total,
    dealer_sales_usable = excluded.dealer_sales_usable,
    dealer_sales_total = excluded.dealer_sales_total,
    competitor_sales_usable = excluded.competitor_sales_usable,
    competitor_sales_total = excluded.competitor_sales_total,
    internal_history_usable = excluded.internal_history_usable,
    internal_history_total = excluded.internal_history_total,
    latest_proof_run_id = excluded.latest_proof_run_id,
    latest_proof_head_sha = excluded.latest_proof_head_sha,
    last_seen_at = excluded.last_seen_at,
    resolved_at = excluded.resolved_at
  returning * into saved_request;

  insert into public.pricing_recovery_request_events (
    request_id,
    event_type,
    previous_queue_status,
    next_queue_status,
    actor,
    reason,
    proof_run_id,
    head_sha,
    metadata
  )
  values (
    saved_request.id,
    event_payload->>'event_type',
    nullif(event_payload->>'previous_queue_status', ''),
    nullif(event_payload->>'next_queue_status', ''),
    nullif(event_payload->>'actor', ''),
    nullif(event_payload->>'reason', ''),
    nullif(event_payload->>'proof_run_id', ''),
    nullif(event_payload->>'head_sha', ''),
    coalesce(event_payload->'metadata', '{}'::jsonb)
  );

  return to_jsonb(saved_request);
end;
$$;

revoke all on function public.sync_pricing_recovery_request(jsonb, jsonb)
  from public, anon, authenticated;

grant execute on function public.sync_pricing_recovery_request(jsonb, jsonb) to service_role;

revoke all on function public.get_pricing_recovery_request_by_group_key(text)
  from public, anon, authenticated;

grant execute on function public.get_pricing_recovery_request_by_group_key(text) to service_role;

notify pgrst, 'reload schema';

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

notify pgrst, 'reload schema';

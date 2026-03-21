-- RLS policies for recon_evaluations and sniper_targets
-- These tables were missing RLS; adding before dealer onboarding.

-- recon_evaluations
ALTER TABLE recon_evaluations ENABLE ROW LEVEL SECURITY;

CREATE POLICY recon_evaluations_select ON recon_evaluations
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY recon_evaluations_insert ON recon_evaluations
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY recon_evaluations_update ON recon_evaluations
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- sniper_targets
ALTER TABLE sniper_targets ENABLE ROW LEVEL SECURITY;

CREATE POLICY sniper_targets_select ON sniper_targets
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY sniper_targets_insert ON sniper_targets
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY sniper_targets_update ON sniper_targets
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY sniper_targets_delete ON sniper_targets
    FOR DELETE USING (auth.uid() = user_id);

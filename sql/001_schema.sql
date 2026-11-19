-- Document Engine schema. Idempotent: safe to run again after every pull.
-- All state lives here. Nothing the engine needs is held only in process memory.

CREATE TABLE IF NOT EXISTS flows (
    flow_id      text PRIMARY KEY,
    name         text NOT NULL,
    description  text NOT NULL DEFAULT '',
    graph        jsonb NOT NULL,                 -- the working draft
    version      int  NOT NULL DEFAULT 0,        -- last saved version number (0 = never saved)
    published_version int,
    is_sample    boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS flow_versions (
    flow_id    text NOT NULL REFERENCES flows ON DELETE CASCADE,
    version    int  NOT NULL,
    name       text NOT NULL,
    graph      jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (flow_id, version)
);

CREATE TABLE IF NOT EXISTS documents (
    document_id text PRIMARY KEY,
    name        text NOT NULL,
    pages       int  NOT NULL,
    size_bytes  bigint NOT NULL,
    sha256      text NOT NULL,
    is_sample   boolean NOT NULL DEFAULT false,
    content     bytea NOT NULL,                  -- the file. Instances share no disk, so files live here.
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- kind: pdf | image | text. For an image, content is the prepared image; for text, UTF-8 with a form feed
-- between pages. page_tokens: estimated input tokens per page (null = the model's figure for a PDF page).
ALTER TABLE documents ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'pdf';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS media_type text NOT NULL DEFAULT 'application/pdf';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_tokens real;
-- via_api: sent by a caller of the public endpoint. Listed on the Files screen, left out of the builder's pickers.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS via_api boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS jobs (
    job_id        text PRIMARY KEY,
    flow_id       text,
    flow_name     text NOT NULL,
    flow_version  int,
    graph         jsonb NOT NULL,                -- snapshot of the flow this job runs
    document_id   text NOT NULL,
    document_name text NOT NULL,
    pages         int  NOT NULL,
    priority      text NOT NULL DEFAULT 'interactive',   -- interactive | bulk
    priority_rank int  NOT NULL DEFAULT 0,               -- 0 interactive, 1 bulk
    state         text NOT NULL DEFAULT 'queued',        -- queued | running | done | failed | cancelled
    label         text NOT NULL DEFAULT '',
    error         text,
    next_seq      int  NOT NULL DEFAULT 0,
    submitted_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at    timestamptz,
    finished_at   timestamptz
);
CREATE INDEX IF NOT EXISTS jobs_submitted_idx ON jobs (submitted_at DESC);
-- One document per source of the flow: {source node id: {document_id, name, pages}}.
-- document_id / document_name / pages above describe the first source (and the page total).
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS documents jsonb NOT NULL DEFAULT '{}'::jsonb;
-- The value inputs this job ran with, {input name: value}. Already written into the job's graph.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS input_values jsonb NOT NULL DEFAULT '{}'::jsonb;

-- One row per step or output node of a job's flow.
CREATE TABLE IF NOT EXISTS job_steps (
    job_id      text NOT NULL REFERENCES jobs ON DELETE CASCADE,
    node_id     text NOT NULL,
    node_type   text NOT NULL,                   -- source | step | output
    title       text NOT NULL,
    instruction text,                            -- map | reduce | filter (how its input arrives)
    model       text,
    state       text NOT NULL DEFAULT 'waiting', -- waiting | running | done | failed | cancelled
    items_in    int,                             -- items offered by the upstream node
    items_kept  int,                             -- after a filter
    tasks_total int NOT NULL DEFAULT 0,
    tasks_done  int NOT NULL DEFAULT 0,
    items       jsonb,                           -- output items once done: [{pages, task_id, src}] (text stays in tasks)
    started_at  timestamptz,
    finished_at timestamptz,
    PRIMARY KEY (job_id, node_id)
);

-- Set when a step's tasks have been created. A step is planned once its input and every reference are done.
ALTER TABLE job_steps ADD COLUMN IF NOT EXISTS planned boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS tasks (
    task_id          bigserial PRIMARY KEY,
    job_id           text NOT NULL REFERENCES jobs ON DELETE CASCADE,
    node_id          text NOT NULL,
    kind             text NOT NULL DEFAULT 'call',      -- call | warmup
    seq              int  NOT NULL,                     -- creation order within the job
    state            text NOT NULL DEFAULT 'ready',     -- waiting | ready | running | lost | done | failed | cancelled
    model            text NOT NULL,
    priority_rank    int  NOT NULL,
    job_submitted_at timestamptz NOT NULL,
    gate_task_id     bigint,                            -- warm-up that must finish first
    pages            int[] NOT NULL DEFAULT '{}',       -- source pages this task covers
    payload          jsonb NOT NULL DEFAULT '{}',       -- {consume, src, sources: [task ids whose output is the input], refs}
    max_tokens       int  NOT NULL,
    expected_output  double precision NOT NULL,
    input_estimate   double precision NOT NULL,
    profile_key      text,
    attempts         int NOT NULL DEFAULT 0,            -- transient failures and invalid replies
    rejections       int NOT NULL DEFAULT 0,            -- 429s. Never consume an attempt.
    lease_owner      text,
    lease_expires_at timestamptz,
    reservation_id   bigint,
    output_text      text,
    output_data      jsonb,
    output_tokens    int,
    stop_reason      text,
    error            text,
    created_at       timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at       timestamptz,
    finished_at      timestamptz
);
-- A call that failed with a gateway error is not sent again before this time.
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS not_before timestamptz;
-- How many times this call was returned to the queue because its worker was lost or its lease ran out.
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS recoveries int NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS tasks_ready_idx ON tasks (model, priority_rank, job_submitted_at, seq, task_id) WHERE state = 'ready';
CREATE INDEX IF NOT EXISTS tasks_job_idx ON tasks (job_id, node_id);
CREATE INDEX IF NOT EXISTS tasks_running_idx ON tasks (lease_expires_at) WHERE state = 'running';
CREATE INDEX IF NOT EXISTS tasks_gate_idx ON tasks (gate_task_id) WHERE state = 'waiting';
CREATE INDEX IF NOT EXISTS tasks_lost_idx ON tasks (task_id) WHERE state = 'lost';
CREATE INDEX IF NOT EXISTS tasks_warmup_idx ON tasks (model) WHERE kind = 'warmup' AND state IN ('ready', 'running');

-- One row per model: its limits (copied from configuration at startup) and the ledger state.
-- This row is the single authority on what may be sent. Admission and completion lock it.
CREATE TABLE IF NOT EXISTS quota (
    model           text PRIMARY KEY,
    gateway_name    text NOT NULL DEFAULT '',
    itpm            double precision NOT NULL DEFAULT 0,
    otpm            double precision NOT NULL DEFAULT 0,
    qph             double precision NOT NULL DEFAULT 0,
    out_capacity    double precision NOT NULL DEFAULT 0,   -- output cap, safety margin already applied
    in_capacity     double precision NOT NULL DEFAULT 0,
    capacity_mode   text NOT NULL DEFAULT 'fixed',         -- fixed | duration
    bucket_measured double precision NOT NULL DEFAULT 0,   -- duration mode: the gateway's own bucket
    default_call_s  double precision NOT NULL DEFAULT 9,
    safety_margin   double precision NOT NULL DEFAULT 0.05,
    hold_s          double precision NOT NULL DEFAULT 1,
    learn           boolean NOT NULL DEFAULT true,
    hold_until      timestamptz,
    out_level       double precision NOT NULL DEFAULT 0,   -- output charged at completion, draining at otpm/60 per second
    in_level        double precision NOT NULL DEFAULT 0,   -- counted input, added at admission, corrected at completion
    updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    admissions      bigint NOT NULL DEFAULT 0,
    blocked_checks  bigint NOT NULL DEFAULT 0,
    rejections      bigint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reservations (
    reservation_id bigserial PRIMARY KEY,
    task_id        bigint NOT NULL,
    job_id         text NOT NULL,
    model          text NOT NULL,
    worker_id      text NOT NULL,
    admitted_at    timestamptz NOT NULL,
    released_at    timestamptz,
    counted_output double precision NOT NULL,   -- while open: expected output. After: actual.
    counted_input  double precision NOT NULL,   -- while open: estimate. After: actual counted input.
    outcome        text
);
CREATE INDEX IF NOT EXISTS reservations_open_idx ON reservations (model) WHERE released_at IS NULL;
CREATE INDEX IF NOT EXISTS reservations_admitted_idx ON reservations (model, admitted_at);
CREATE INDEX IF NOT EXISTS reservations_released_idx ON reservations (model, released_at);

-- Learned per-step profile: what a call of this flow step, model and thinking setting really costs.
CREATE TABLE IF NOT EXISTS profiles (
    profile_key text PRIMARY KEY,                -- flow_id:node_id:model:thinking
    n           int NOT NULL DEFAULT 0,
    out_mean    double precision NOT NULL DEFAULT 0,
    out_var     double precision NOT NULL DEFAULT 0,
    out_max     double precision NOT NULL DEFAULT 0,
    in_mean     double precision NOT NULL DEFAULT 0,   -- counted input per call (cache reads excluded)
    dur_mean    double precision NOT NULL DEFAULT 0,   -- seconds
    truncated   int NOT NULL DEFAULT 0,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Every model call, successful or not.
CREATE TABLE IF NOT EXISTS calls (
    call_id        bigserial PRIMARY KEY,
    task_id        bigint,
    job_id         text,
    node_id        text,
    model          text NOT NULL,
    kind           text NOT NULL DEFAULT 'call',
    thinking       text,
    sent_at        timestamptz NOT NULL,
    first_token_at timestamptz,
    done_at        timestamptz NOT NULL,
    request_bytes  bigint,
    http_status    int,
    outcome        text NOT NULL,                -- ok | 429 | transient | permanent | refusal | empty | invalid
    limit_type     text,
    stop_reason    text,
    input_tokens   int,
    output_tokens  int,
    cache_read     int,
    cache_write    int,
    truncated      boolean NOT NULL DEFAULT false,
    request_id     text,
    error          jsonb
);
CREATE INDEX IF NOT EXISTS calls_job_idx ON calls (job_id);
CREATE INDEX IF NOT EXISTS calls_done_idx ON calls (model, done_at);

-- Every state change. This table is the measurement system and the source of the live views.
CREATE TABLE IF NOT EXISTS events (
    event_id bigserial PRIMARY KEY,
    ts       timestamptz NOT NULL DEFAULT clock_timestamp(),
    kind     text NOT NULL,
    job_id   text,
    node_id  text,
    task_id  bigint,
    model    text,
    data     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_job_idx ON events (job_id, event_id);

-- Warm cache entries, so jobs that share a model and static prompt share one warm-up.
CREATE TABLE IF NOT EXISTS cache_warm (
    model       text NOT NULL,
    prefix_hash text NOT NULL,
    warmed_at   timestamptz NOT NULL,
    PRIMARY KEY (model, prefix_hash)
);

-- Live worker processes. A task whose owner stopped heartbeating is returned to the queue.
CREATE TABLE IF NOT EXISTS workers (
    worker_id    text PRIMARY KEY,
    started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    heartbeat_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    info         jsonb NOT NULL DEFAULT '{}'
);

-- ---------------------------------------------------------------------------------------------
-- The pause after a rejection grows while rejections keep coming: hold_s, then twice that, and so on
-- up to hold_max_s. hold_streak counts the rounds in a row that ended in a rejection.
ALTER TABLE quota ADD COLUMN IF NOT EXISTS hold_max_s double precision NOT NULL DEFAULT 15;
ALTER TABLE quota ADD COLUMN IF NOT EXISTS hold_streak int NOT NULL DEFAULT 0;
-- The output cap the last admission check used. In `duration` mode it depends on the step being admitted.
ALTER TABLE quota ADD COLUMN IF NOT EXISTS cap_used double precision;

-- Calls admitted per model and minute. The queries-per-hour check adds up at most 61 rows of this table;
-- counting an hour of reservations on every admission got slower as volume grew.
CREATE TABLE IF NOT EXISTS quota_minutes (
    model  text NOT NULL,
    minute timestamptz NOT NULL,
    n      int NOT NULL DEFAULT 0,
    PRIMARY KEY (model, minute)
);
-- First start after an upgrade: fill the last hour from the reservations, once.
INSERT INTO quota_minutes (model, minute, n)
    SELECT model, date_trunc('minute', admitted_at), count(*) FROM reservations
    WHERE admitted_at > clock_timestamp() - interval '61 minutes'
      AND NOT EXISTS (SELECT 1 FROM quota_minutes)
    GROUP BY 1, 2
    ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------------------------
-- Admission in one round trip.
--
-- Every quota row is locked, in model order, so admission never deadlocks with itself. Each model
-- has one queue: interactive before bulk, then job submission time, then task order. The models'
-- head tasks are tried in that same order across models, so an interactive call on one model goes
-- before a bulk call on another when a worker has one free slot. The head is strict: if it does not
-- fit, nothing behind it on that model is sent, and the next model's head is tried.
-- A call waiting to be retried (not_before in the future) is skipped until its time comes.
--
-- What the gateway does (measured 2026-11-14 to 16): it reserves nothing at admission, charges
-- actual output when a call completes, and behaves like a token bucket refilling at OTPM/60 per
-- second. So the ledger keeps out_level (charged output, draining) and counts every in-flight call
-- at its expected output until it completes.
--
-- Returns {kind: admitted, task, reservation_id, detail}
--      or {kind: blocked | held | empty, wait_s, detail}.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION de_admit(p_worker_id text, p_lease_s double precision)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
    q quota%ROWTYPE;
    t tasks%ROWTYPE;
    p profiles%ROWTYPE;
    t0 timestamptz := clock_timestamp();
    now_db timestamptz;
    dt double precision;
    v_out double precision;
    v_in double precision;
    open_output double precision;
    open_calls int;
    q_hour bigint;
    rate double precision;
    cap double precision;
    expected double precision;
    out_count double precision;
    est_in double precision;
    excess double precision;
    w double precision;
    best_wait double precision := NULL;
    saw_ready boolean := false;
    last_reason text := NULL;
    last_detail jsonb := NULL;
    reason text;
    res_id bigint;
    started text;
    detail jsonb;
BEGIN
    PERFORM 1 FROM quota ORDER BY model FOR UPDATE;
    FOR q IN
        SELECT qq.* FROM quota qq
        JOIN LATERAL (
            SELECT tt.priority_rank, tt.job_submitted_at FROM tasks tt
            WHERE tt.model = qq.model AND tt.state = 'ready'
              AND (tt.not_before IS NULL OR tt.not_before <= clock_timestamp())
            ORDER BY tt.priority_rank, tt.job_submitted_at, tt.seq, tt.task_id LIMIT 1
        ) h ON true
        ORDER BY h.priority_rank, h.job_submitted_at, qq.model
    LOOP
        -- SKIP LOCKED: a call that another transaction is changing right now (a job being cancelled, say) is
        -- passed over, so admission never waits on a row lock while it holds the quota rows.
        SELECT * INTO t FROM tasks WHERE model = q.model AND state = 'ready'
              AND (not_before IS NULL OR not_before <= clock_timestamp())
            ORDER BY priority_rank, job_submitted_at, seq, task_id LIMIT 1
            FOR UPDATE SKIP LOCKED;
        IF NOT FOUND THEN
            CONTINUE;
        END IF;
        saw_ready := true;
        now_db := clock_timestamp();

        IF q.hold_until IS NOT NULL AND q.hold_until > now_db THEN
            w := extract(epoch FROM q.hold_until - now_db);
            best_wait := least(coalesce(best_wait, w), w);
            last_reason := 'held';
            last_detail := jsonb_build_object('model', q.model, 'hold_s', w, 'task_id', t.task_id);
            UPDATE quota SET blocked_checks = blocked_checks + 1 WHERE model = q.model;
            CONTINUE;
        END IF;

        rate := greatest(q.otpm, 1) / 60.0;
        dt := greatest(0, extract(epoch FROM now_db - q.updated_at));
        v_out := greatest(0, q.out_level - dt * rate);
        v_in := greatest(0, q.in_level - dt * greatest(q.itpm, 1) / 60.0);

        SELECT coalesce(sum(counted_output), 0), count(*) INTO open_output, open_calls
            FROM reservations WHERE model = q.model AND released_at IS NULL;

        -- What this call counts while it is in flight: the learned mean when there is one,
        -- otherwise the step's configured expectation. max_tokens is only the truncation guard.
        p := NULL;
        IF t.profile_key IS NOT NULL THEN
            SELECT * INTO p FROM profiles WHERE profile_key = t.profile_key;
        END IF;
        expected := t.expected_output;
        IF q.learn AND p.n IS NOT NULL AND p.n >= 3 THEN
            expected := p.out_mean;
        END IF;
        out_count := least(t.max_tokens, greatest(1, round(expected)));
        est_in := t.input_estimate;

        cap := q.out_capacity;
        IF q.capacity_mode = 'duration' THEN
            -- In-flight calls are charged when they complete, on average half a call duration from now,
            -- and the bucket refills in the meantime. So the cap is the bucket plus half a call of refill.
            cap := (q.bucket_measured + rate * 0.5 * CASE WHEN q.learn AND p.n IS NOT NULL AND p.n >= 3 AND p.dur_mean > 0
                                                          THEN p.dur_mean ELSE q.default_call_s END)
                   * (1 - q.safety_margin);
        END IF;

        reason := NULL;
        -- A call larger than the whole cap is still sent when nothing else is in the way,
        -- otherwise it could never run.
        IF v_out + open_output + out_count > cap AND NOT (open_calls = 0 AND v_out <= 0) THEN
            reason := 'output';
            excess := v_out + open_output + out_count - cap;
            w := CASE WHEN excess <= v_out THEN excess / rate ELSE 0.5 END;
        ELSIF v_in + est_in > q.in_capacity AND NOT (open_calls = 0 AND v_in <= 0) THEN
            reason := 'input';
            excess := v_in + est_in - q.in_capacity;
            w := excess / (greatest(q.itpm, 1) / 60.0);
        ELSIF q.qph > 0 THEN
            -- Whole minutes, so up to one minute more than the hour is counted: the check errs on the safe side.
            SELECT coalesce(sum(n), 0) INTO q_hour FROM quota_minutes
                WHERE model = q.model AND minute > now_db - interval '61 minutes';
            IF q_hour + 1 > q.qph THEN
                reason := 'queries';
                w := 1.0;
            END IF;
        END IF;

        detail := jsonb_build_object(
            'model', q.model, 'task_id', t.task_id, 'out_level', round(v_out), 'open_output', round(open_output),
            'open_calls', open_calls, 'counted_output', out_count, 'cap', round(cap),
            'in_level', round(v_in), 'input_estimate', round(est_in));

        IF reason IS NOT NULL THEN
            w := least(greatest(w, 0.05), 1.0);
            best_wait := least(coalesce(best_wait, w), w);
            last_reason := reason;
            last_detail := detail;
            UPDATE quota SET blocked_checks = blocked_checks + 1, cap_used = cap WHERE model = q.model;
            CONTINUE;
        END IF;

        INSERT INTO reservations (task_id, job_id, model, worker_id, admitted_at, counted_output, counted_input)
            VALUES (t.task_id, t.job_id, q.model, p_worker_id, now_db, out_count, est_in)
            RETURNING reservation_id INTO res_id;
        UPDATE tasks SET state = 'running', lease_owner = p_worker_id,
                lease_expires_at = now_db + make_interval(secs => p_lease_s),
                started_at = coalesce(started_at, now_db), reservation_id = res_id
            WHERE task_id = t.task_id;
        UPDATE quota SET out_level = v_out, in_level = v_in + est_in, updated_at = now_db,
                admissions = admissions + 1, cap_used = cap
            WHERE model = q.model;
        INSERT INTO quota_minutes AS m (model, minute, n) VALUES (q.model, date_trunc('minute', now_db), 1)
            ON CONFLICT (model, minute) DO UPDATE SET n = m.n + 1;
        UPDATE jobs SET state = 'running', started_at = now_db
            WHERE job_id = t.job_id AND started_at IS NULL RETURNING job_id INTO started;
        IF started IS NOT NULL THEN
            INSERT INTO events (ts, kind, job_id, data) VALUES (now_db, 'job_started', t.job_id, '{}'::jsonb);
        END IF;
        UPDATE job_steps SET state = 'running', started_at = coalesce(started_at, now_db)
            WHERE job_id = t.job_id AND node_id = t.node_id AND state = 'waiting';
        INSERT INTO events (ts, kind, job_id, node_id, task_id, model, data)
            VALUES (now_db, 'task_admitted', t.job_id, t.node_id, t.task_id, q.model,
                    jsonb_build_object('kind', t.kind, 'pages', to_jsonb(t.pages), 'counted_output', out_count,
                                       'open_calls', open_calls + 1));
        RETURN jsonb_build_object(
            'kind', 'admitted', 'task', to_jsonb(t), 'reservation_id', res_id, 'detail', detail,
            'admit_db_ms', extract(epoch FROM clock_timestamp() - t0) * 1000);
    END LOOP;

    IF NOT saw_ready THEN
        -- Nothing can be sent now. If calls are waiting to be retried, say when the first one is due.
        SELECT extract(epoch FROM min(not_before) - clock_timestamp()) INTO w
            FROM tasks WHERE state = 'ready' AND not_before > clock_timestamp();
        IF w IS NOT NULL THEN
            RETURN jsonb_build_object('kind', 'blocked', 'reason', 'retry_wait',
                                      'wait_s', least(greatest(w, 0.05), 1.0));
        END IF;
        RETURN jsonb_build_object('kind', 'empty');
    END IF;
    RETURN jsonb_build_object('kind', CASE WHEN last_reason = 'held' THEN 'held' ELSE 'blocked' END,
                              'reason', last_reason, 'wait_s', coalesce(best_wait, 0.25), 'detail', last_detail);
END;
$$;

-- ---------------------------------------------------------------------------------------------
-- Completion. Uses the same clock and the same drain arithmetic as admission.
--
-- The level is drained to "now" before the actual output is added. Adding to a stale level would
-- clamp at zero too late and under-count after an idle period.
--
-- A rejected or failed call adds nothing: it produced no output. (The POC fell back to max_tokens
-- here, which would have stalled admission during a run of rejections.)
-- A 429 pauses admission for this model, for every worker. The first pause lasts hold_s seconds. If
-- a call sent after that pause is rejected too, the next pause is twice as long, and so on up to
-- hold_max_s: a short blip costs one short pause, and a gateway that keeps rejecting is left alone
-- for longer each time. Calls that were already in flight when a pause began do not lengthen the
-- steps. The first call accepted after a pause puts the pause back to hold_s.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION de_release(
    p_reservation_id bigint, p_outcome text, p_actual_output double precision, p_counted_input double precision
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    r reservations%ROWTYPE;
    q quota%ROWTYPE;
    now_db timestamptz;
    dt double precision;
    v_out double precision;
    v_in double precision;
    new_round boolean;
    streak int;
    pause double precision;
BEGIN
    SELECT * INTO r FROM reservations WHERE reservation_id = p_reservation_id FOR UPDATE;
    IF NOT FOUND OR r.released_at IS NOT NULL THEN
        RETURN;
    END IF;
    SELECT * INTO q FROM quota WHERE model = r.model FOR UPDATE;
    now_db := clock_timestamp();
    v_out := greatest(0, coalesce(p_actual_output, 0));
    v_in := greatest(0, coalesce(p_counted_input, CASE WHEN p_outcome = 'ok' THEN r.counted_input ELSE 0 END));
    IF FOUND THEN
        dt := greatest(0, extract(epoch FROM now_db - q.updated_at));
        -- A new round: this call was sent after the last pause ended (or there has been none).
        new_round := q.hold_until IS NULL OR r.admitted_at >= q.hold_until;
        streak := q.hold_streak;
        IF p_outcome = '429' THEN
            IF new_round OR streak = 0 THEN
                streak := streak + 1;
            END IF;
        ELSIF p_outcome = 'ok' AND new_round THEN
            streak := 0;
        END IF;
        pause := least(greatest(q.hold_max_s, q.hold_s), q.hold_s * power(2, greatest(streak - 1, 0)));
        UPDATE quota SET
            hold_streak = streak,
            out_level = greatest(0, q.out_level - dt * greatest(q.otpm, 1) / 60.0) + v_out,
            in_level = greatest(0, greatest(0, q.in_level - dt * greatest(q.itpm, 1) / 60.0) + v_in - r.counted_input),
            updated_at = now_db,
            rejections = rejections + CASE WHEN p_outcome = '429' THEN 1 ELSE 0 END,
            hold_until = CASE WHEN p_outcome = '429'
                              THEN greatest(coalesce(q.hold_until, now_db), now_db + make_interval(secs => pause))
                              ELSE q.hold_until END
            WHERE model = r.model;
    END IF;
    UPDATE reservations SET released_at = now_db, outcome = p_outcome, counted_output = v_out, counted_input = v_in
        WHERE reservation_id = p_reservation_id;
    PERFORM pg_notify('de_wake', r.model);
END;
$$;

-- Returns tasks to the queue when their lease ran out or their worker stopped heartbeating.
-- The lost call may still complete and be charged at the gateway, so its expected output is kept in the level.
-- A call returned more than p_max_recoveries times is not queued again: it is set to 'lost', which no admission
-- picks up, and the worker then fails its job. 0 means no limit.
DROP FUNCTION IF EXISTS de_reap(double precision);
CREATE OR REPLACE FUNCTION de_reap(p_dead_after_s double precision, p_max_recoveries int DEFAULT 0)
RETURNS int LANGUAGE plpgsql AS $$
DECLARE
    t record;
    n int := 0;
    r reservations%ROWTYPE;
BEGIN
    FOR t IN
        SELECT tk.task_id, tk.job_id, tk.node_id, tk.model, tk.reservation_id, tk.lease_owner, tk.recoveries
        FROM tasks tk LEFT JOIN workers w ON w.worker_id = tk.lease_owner
        WHERE tk.state = 'running'
          AND (tk.lease_expires_at < clock_timestamp()
               OR w.worker_id IS NULL
               OR w.heartbeat_at < clock_timestamp() - make_interval(secs => p_dead_after_s))
        FOR UPDATE OF tk SKIP LOCKED
    LOOP
        IF t.reservation_id IS NOT NULL THEN
            SELECT * INTO r FROM reservations WHERE reservation_id = t.reservation_id;
            PERFORM de_release(t.reservation_id, 'expired', r.counted_output, r.counted_input);
        END IF;
        UPDATE tasks SET state = CASE WHEN p_max_recoveries > 0 AND t.recoveries + 1 > p_max_recoveries
                                      THEN 'lost' ELSE 'ready' END,
                lease_owner = NULL, lease_expires_at = NULL, reservation_id = NULL, recoveries = recoveries + 1
            WHERE task_id = t.task_id;
        INSERT INTO events (kind, job_id, node_id, task_id, model, data)
            VALUES ('task_recovered', t.job_id, t.node_id, t.task_id, t.model,
                    jsonb_build_object('previous_owner', t.lease_owner));
        n := n + 1;
    END LOOP;
    DELETE FROM quota_minutes WHERE minute < clock_timestamp() - interval '3 hours';
    IF n > 0 THEN
        PERFORM pg_notify('de_wake', 'reap');
    END IF;
    RETURN n;
END;
$$;

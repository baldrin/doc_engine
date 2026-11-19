-- Removes every Document Engine table and function. All flows, documents, jobs and history are lost.
DROP FUNCTION IF EXISTS de_admit(text, double precision);
DROP FUNCTION IF EXISTS de_release(bigint, text, double precision, double precision);
DROP FUNCTION IF EXISTS de_reap(double precision);
DROP TABLE IF EXISTS workers, cache_warm, events, calls, profiles, reservations, quota, tasks, job_steps, jobs,
    documents, flow_versions, flows CASCADE;

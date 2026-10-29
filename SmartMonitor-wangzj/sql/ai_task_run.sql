-- PostgreSQL lifecycle state for dynamic MediaMTX / ai-stream task runs.
create table if not exists ai_task_run (
    run_id varchar(64) primary key,
    camera_id bigint not null,
    task_code varchar(64) not null,
    status varchar(16) not null,
    input_path varchar(255) not null,
    output_path varchar(255) not null,
    output_url text not null,
    failure_reason text,
    started_at timestamptz,
    stopped_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_ai_task_run_camera_status on ai_task_run(camera_id, status);
create index if not exists idx_ai_task_run_camera_task_status on ai_task_run(camera_id, task_code, status);

CREATE TABLE IF NOT EXISTS public.channel (
    channel_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS public.sample (
    channel_id BIGINT NOT NULL REFERENCES public.channel(channel_id),
    smpl_time TIMESTAMPTZ NOT NULL,
    nanosecs INTEGER NOT NULL DEFAULT 0,
    float_val DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS public.sample_raw (
    channel_id BIGINT NOT NULL REFERENCES public.channel(channel_id),
    smpl_time TIMESTAMPTZ NOT NULL,
    nanosecs INTEGER NOT NULL DEFAULT 0,
    num_val DOUBLE PRECISION,
    severity_id INTEGER,
    status_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_channel_name ON public.channel (name);
CREATE INDEX IF NOT EXISTS idx_sample_channel_time ON public.sample (channel_id, smpl_time);
CREATE INDEX IF NOT EXISTS idx_sample_raw_channel_time ON public.sample_raw (channel_id, smpl_time);

INSERT INTO public.channel (name)
VALUES
    ('RNG:BEAM:CURR'),
    ('RNG:BEAM:CURRENT'),
    ('SR_PS_QM01:current:ai')
ON CONFLICT (name) DO NOTHING;

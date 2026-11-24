BEGIN;

ALTER TABLE public.pins
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS route_order INTEGER;

UPDATE public.pins
SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP)
WHERE created_at IS NULL;

WITH project_max AS (
  SELECT project_id, COALESCE(MAX(route_order), 0) AS max_route_order
  FROM public.pins
  WHERE route_order IS NOT NULL AND route_order <> 0
  GROUP BY project_id
),
unsequenced AS (
  SELECT pin.id,
         ROW_NUMBER() OVER (
           PARTITION BY pin.project_id
           ORDER BY pin.created_at, pin.id
         )::integer AS fallback_route_order,
         COALESCE(project_max.max_route_order, 0) AS max_route_order
  FROM public.pins AS pin
  LEFT JOIN project_max ON project_max.project_id = pin.project_id
  WHERE pin.route_order IS NULL OR pin.route_order = 0
)
UPDATE public.pins AS pin
SET route_order = unsequenced.max_route_order + unsequenced.fallback_route_order
FROM unsequenced
WHERE pin.id = unsequenced.id;

ALTER TABLE public.pins
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN route_order SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_pins_project_route_unique
  ON public.pins(project_id, route_order);
CREATE INDEX IF NOT EXISTS idx_pins_project_route
  ON public.pins(project_id, route_order, created_at, id);

COMMIT;

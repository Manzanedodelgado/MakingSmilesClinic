-- 31-oct-2026: hora REAL de 71 mensajes de WhatsApp que se guardaron con la hora de llegada a Making
-- (reenviados tras una caída: el webhook usaba now()). La hora real es el messageTimestamp que Evolution
-- guarda en su BD (tabla "Message"); se corrige solo cuando es ANTERIOR a la llegada (lo contrario es imposible)
-- y solo si el valor actual es el esperado (guarda anti-doble aplicación). Se fijan enviado_at y created_at, igual
-- que hace ya el webhook con la hora real. Después se recalcula ultimo_mensaje_at de las conversaciones afectadas.
-- No toca movimientos_bancarios ni ningún importe.
WITH c(id, real_ts, old_ts) AS (VALUES
  (88, '2026-09-09 07:46:16'::timestamp, '2026-09-09 08:07:24.192273'::timestamp),
  (90, '2026-09-09 07:56:30'::timestamp, '2026-09-09 08:17:28.896513'::timestamp),
  (124, '2026-09-10 09:54:08'::timestamp, '2026-09-10 10:09:20.545925'::timestamp),
  (185, '2026-09-10 14:55:02'::timestamp, '2026-09-10 15:00:15.034745'::timestamp),
  (1522, '2026-07-21 07:48:11'::timestamp, '2026-07-24 10:15:13.300313'::timestamp),
  (1523, '2026-07-21 14:58:06'::timestamp, '2026-07-24 10:15:13.932129'::timestamp),
  (1524, '2026-07-22 16:34:12'::timestamp, '2026-07-24 10:15:14.544724'::timestamp),
  (1525, '2026-07-23 10:35:02'::timestamp, '2026-07-24 10:15:14.744489'::timestamp),
  (1526, '2026-07-23 12:45:56'::timestamp, '2026-07-24 10:15:15.085073'::timestamp),
  (1527, '2026-07-24 07:35:07'::timestamp, '2026-07-24 10:15:15.498140'::timestamp),
  (1841, '2026-08-05 14:54:55'::timestamp, '2026-08-05 23:47:34.319221'::timestamp),
  (1842, '2026-08-05 17:40:13'::timestamp, '2026-08-05 23:47:34.829604'::timestamp),
  (1843, '2026-08-05 17:40:26'::timestamp, '2026-08-05 23:47:35.194333'::timestamp),
  (1992, '2026-09-10 14:57:15'::timestamp, '2026-09-10 15:02:33.523802'::timestamp),
  (2034, '2026-09-14 09:01:00'::timestamp, '2026-09-15 06:00:31.444783'::timestamp),
  (2035, '2026-09-14 10:52:25'::timestamp, '2026-09-15 06:00:31.786641'::timestamp),
  (2036, '2026-09-14 12:32:55'::timestamp, '2026-09-15 06:00:32.018246'::timestamp),
  (2037, '2026-09-14 15:58:04'::timestamp, '2026-09-15 06:00:32.362514'::timestamp),
  (2212, '2026-09-17 10:27:01'::timestamp, '2026-09-17 10:38:55.796111'::timestamp),
  (2214, '2026-09-17 10:24:31'::timestamp, '2026-09-17 10:41:28.256873'::timestamp),
  (2215, '2026-09-17 10:24:16'::timestamp, '2026-09-17 10:41:40.208323'::timestamp),
  (2247, '2026-09-17 17:27:46'::timestamp, '2026-09-17 17:58:46.970298'::timestamp),
  (2284, '2026-09-18 15:29:16'::timestamp, '2026-09-19 14:27:26.788951'::timestamp),
  (2285, '2026-09-18 15:53:25'::timestamp, '2026-09-19 14:27:27.535574'::timestamp),
  (2361, '2026-09-23 16:19:51'::timestamp, '2026-09-25 01:59:08.036723'::timestamp),
  (2362, '2026-09-23 16:59:53'::timestamp, '2026-09-25 01:59:08.237679'::timestamp),
  (2363, '2026-09-24 09:11:29'::timestamp, '2026-09-25 01:59:08.413171'::timestamp),
  (2364, '2026-09-23 15:47:03'::timestamp, '2026-09-25 01:59:08.472967'::timestamp),
  (2365, '2026-09-23 16:20:10'::timestamp, '2026-09-25 01:59:08.690516'::timestamp),
  (2366, '2026-09-24 15:19:57'::timestamp, '2026-09-25 01:59:08.785352'::timestamp),
  (2367, '2026-09-24 15:18:23'::timestamp, '2026-09-25 01:59:09.168347'::timestamp),
  (2484, '2026-09-29 10:59:26'::timestamp, '2026-09-30 18:36:46.212068'::timestamp),
  (2485, '2026-09-29 12:28:53'::timestamp, '2026-09-30 18:36:46.438957'::timestamp),
  (2486, '2026-09-29 14:48:29'::timestamp, '2026-09-30 18:36:46.645262'::timestamp),
  (2487, '2026-09-29 14:48:44'::timestamp, '2026-09-30 18:36:46.842775'::timestamp),
  (2488, '2026-09-30 14:22:22'::timestamp, '2026-09-30 18:36:47.051098'::timestamp),
  (2489, '2026-09-30 14:22:35'::timestamp, '2026-09-30 18:36:47.256279'::timestamp),
  (2583, '2026-10-02 07:19:33'::timestamp, '2026-10-02 07:52:12.778967'::timestamp),
  (2641, '2026-10-07 08:12:07'::timestamp, '2026-10-08 00:55:18.484965'::timestamp),
  (2642, '2026-10-07 09:16:52'::timestamp, '2026-10-08 00:55:19.520721'::timestamp),
  (2643, '2026-10-07 09:16:58'::timestamp, '2026-10-08 00:55:19.803948'::timestamp),
  (2644, '2026-10-07 09:17:12'::timestamp, '2026-10-08 00:55:20.119835'::timestamp),
  (2645, '2026-10-07 09:17:59'::timestamp, '2026-10-08 00:55:20.312159'::timestamp),
  (2646, '2026-10-07 11:57:03'::timestamp, '2026-10-08 00:55:20.754485'::timestamp),
  (2647, '2026-10-07 13:25:55'::timestamp, '2026-10-08 00:55:21.071740'::timestamp),
  (2648, '2026-10-07 13:26:26'::timestamp, '2026-10-08 00:55:21.267002'::timestamp),
  (2649, '2026-10-07 13:27:45'::timestamp, '2026-10-08 00:55:21.708167'::timestamp),
  (2650, '2026-10-07 13:27:57'::timestamp, '2026-10-08 00:55:22.171658'::timestamp),
  (2651, '2026-10-07 13:28:07'::timestamp, '2026-10-08 00:55:22.526046'::timestamp),
  (2652, '2026-10-07 13:27:24'::timestamp, '2026-10-08 00:55:22.881922'::timestamp),
  (2653, '2026-10-07 13:28:39'::timestamp, '2026-10-08 00:55:22.982420'::timestamp),
  (2654, '2026-10-07 13:29:07'::timestamp, '2026-10-08 00:55:23.214064'::timestamp),
  (2655, '2026-10-07 13:30:13'::timestamp, '2026-10-08 00:55:23.505626'::timestamp),
  (2656, '2026-10-07 13:30:14'::timestamp, '2026-10-08 00:55:23.685719'::timestamp),
  (2657, '2026-10-07 13:30:22'::timestamp, '2026-10-08 00:55:23.918540'::timestamp),
  (2658, '2026-10-07 13:31:59'::timestamp, '2026-10-08 00:55:24.215654'::timestamp),
  (2659, '2026-10-07 13:32:06'::timestamp, '2026-10-08 00:55:24.978069'::timestamp),
  (2660, '2026-10-07 14:05:16'::timestamp, '2026-10-08 00:55:25.008399'::timestamp),
  (2661, '2026-10-07 15:40:10'::timestamp, '2026-10-08 00:55:25.277426'::timestamp),
  (2662, '2026-10-07 16:37:04'::timestamp, '2026-10-08 00:55:25.868418'::timestamp),
  (2663, '2026-10-07 18:24:15'::timestamp, '2026-10-08 00:55:26.140429'::timestamp),
  (2664, '2026-10-07 16:36:47'::timestamp, '2026-10-08 00:55:32.848915'::timestamp),
  (2698, '2026-10-13 09:08:38'::timestamp, '2026-10-13 10:43:26.059463'::timestamp),
  (2699, '2026-10-13 09:08:52'::timestamp, '2026-10-13 10:43:26.172248'::timestamp),
  (2700, '2026-10-13 09:08:00'::timestamp, '2026-10-13 10:43:26.176890'::timestamp),
  (2701, '2026-10-13 09:17:27'::timestamp, '2026-10-13 10:43:26.363525'::timestamp),
  (2702, '2026-10-13 10:02:22'::timestamp, '2026-10-13 10:43:26.461585'::timestamp),
  (2779, '2026-10-19 17:06:49'::timestamp, '2026-10-21 07:47:06.801862'::timestamp),
  (2825, '2026-10-26 12:31:36'::timestamp, '2026-10-29 14:44:29.198577'::timestamp),
  (2826, '2026-10-26 14:43:29'::timestamp, '2026-10-29 14:44:29.558240'::timestamp),
  (2827, '2026-10-27 12:46:13'::timestamp, '2026-10-29 14:44:29.992407'::timestamp)
)
UPDATE mensajes m SET enviado_at = c.real_ts, created_at = c.real_ts
  FROM c WHERE m.id = c.id AND m.enviado_at = c.old_ts;

UPDATE conversaciones v SET ultimo_mensaje_at = x.t
  FROM (SELECT conversacion_id, max(enviado_at) AS t FROM mensajes
         WHERE conversacion_id IN (SELECT conversacion_id FROM mensajes WHERE id IN (88,90,124,185,1522,1523,1524,1525,1526,1527,1841,1842,1843,1992,2034,2035,2036,2037,2212,2214,2215,2247,2284,2285,2361,2362,2363,2364,2365,2366,2367,2484,2485,2486,2487,2488,2489,2583,2641,2642,2643,2644,2645,2646,2647,2648,2649,2650,2651,2652,2653,2654,2655,2656,2657,2658,2659,2660,2661,2662,2663,2664,2698,2699,2700,2701,2702,2779,2825,2826,2827))
         GROUP BY conversacion_id) x
 WHERE v.id = x.conversacion_id;

/**
 * TourGuide — page-aware, element-anchored onboarding tour.
 *
 * Rules:
 *  - Every step targets an element that is ALWAYS in the DOM for that page
 *  - If element not found after 3s, the tour tooltip shows centred (never breaks)
 *  - Black button with white text to match app design
 *  - One-time: stored in localStorage. Key bumped on redesign.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const TOUR_KEY = 'axiom_tour_v5_done';

interface TourStep {
  /** pathname this step lives on */
  page: string;
  /** DOM element id to highlight (must exist always on that page) */
  elementId: string;
  title: string;
  description: string;
  /** If set, navigate here when user clicks Next */
  navigateTo?: string;
}

const STEPS: TourStep[] = [
  // ── Dashboard ────────────────────────────────────────────
  {
    page: '/',
    elementId: 'tour-dashboard',
    title: '① Open Dashboard',
    description:
      'This is the main command center. You can see live system metrics — total jobs queued, running, completed, and failed — refreshed every few seconds.',
  },
  // ── Queues page ──────────────────────────────────────────
  {
    page: '/',
    elementId: 'tour-nav-queues',
    title: '② Navigate to Queues',
    description:
      'All job queues are managed here. Click "Next" and we will take you to the Queues page.',
    navigateTo: '/queues',
  },
  {
    page: '/queues',
    elementId: 'tour-create-queue',
    title: '③ Create a Queue',
    description:
      'Click "+ New Queue" to create a queue. Give it a name and choose a retry strategy — Fixed, Linear, or Exponential backoff with jitter.',
  },
  {
    page: '/queues',
    elementId: 'tour-create-queue',
    title: '④ Configure Retry Policy',
    description:
      'Inside the queue form you set max retry attempts and the backoff strategy. Exponential backoff prevents thundering-herd failures during outages.',
  },
  // ── Job Explorer page (navigated by clicking a queue) ────
  {
    page: '/queues',
    elementId: 'tour-queue-link',
    title: '⑤ Open Job Explorer',
    description:
      'Click the first queue link to open its Job Explorer. You can see all jobs, statuses, and retry counts.',
  },
  {
    page: '/queues',
    elementId: 'tour-pause-btn',
    title: '⑥ Pause a Queue',
    description:
      'The Pause button stops workers from picking up NEW jobs. Jobs already running finish gracefully. Great for maintenance windows.',
  },
  {
    page: '/queues',
    elementId: 'tour-pause-btn',
    title: '⑦ Resume a Queue',
    description:
      'Hit Resume (same button) and the queue drains normally. Workers start claiming jobs again immediately without any restart.',
  },
  {
    page: '/queues',
    elementId: 'tour-dlq-btn',
    title: '⑧ Dead Letter Queue',
    description:
      'After max retries, jobs land in the DLQ. Click the "DLQ" button on a queue row to inspect them. No failed job is ever silently dropped.',
  },
  {
    page: '/queues',
    elementId: 'tour-project-select', // Fallback anchor
    title: '⑨ Submit a Job',
    description:
      'Inside Job Explorer, you can hit "Submit Immediate Job". The worker will claim it using SELECT … FOR UPDATE SKIP LOCKED.',
  },
  {
    page: '/queues',
    elementId: 'tour-project-select', // Fallback anchor
    title: '⑩ Watch Job Complete',
    description:
      'Jobs transition: queued → claimed → running → completed. The job explorer refreshes every second so you can watch the state machine live.',
  },
  {
    page: '/queues',
    elementId: 'tour-project-select', // Fallback anchor
    title: '⑪ Submit a Failing Job',
    description:
      'Use "Submit Failing Job" to inject a job that will always error. You will see it retry with the configured backoff.',
  },
  {
    page: '/queues',
    elementId: 'tour-project-select', // Fallback anchor
    title: '⑫ Open Execution Logs',
    description:
      'Click any job row to expand its execution log — full stack traces, timing, and attempt history.',
  },
  {
    page: '/queues',
    elementId: 'tour-project-select', // Fallback anchor
    title: '⑬ Retry a DLQ Job',
    description:
      'From the DLQ, click Retry to re-enqueue a dead job after you have fixed the root cause.',
  },
  // ── Workers page ─────────────────────────────────────────
  {
    page: '/queues',
    elementId: 'tour-nav-workers',
    title: '⑭ Open Worker Monitoring',
    description:
      'The Worker Fleet page shows every active worker: hostname, PID, active job count, and last heartbeat. Stale workers are reaped automatically. Tour complete! 🎉',
    navigateTo: '/workers',
  },
];

// ─── Helpers ────────────────────────────────────────────────────────────────

function calcPopoverPos(rect: DOMRect, wW: number, wH: number) {
  const M = 14;
  const PW = 340;
  const PH = 180;

  let top: number;
  let left: number;

  // prefer below, else above, else middle
  if (rect.bottom + PH + M < wH) top = rect.bottom + M;
  else if (rect.top - PH - M > 0) top = rect.top - PH - M;
  else top = wH / 2 - PH / 2;

  left = rect.left;
  if (left + PW > wW - M) left = wW - PW - M;
  if (left < M) left = M;

  return { top, left };
}

// ─── Component ──────────────────────────────────────────────────────────────

export default function TourGuide() {
  const location = useLocation();
  const navigate = useNavigate();

  const [idx, setIdx] = useState<number | null>(null);
  const [hlStyle, setHlStyle] = useState<React.CSSProperties>({});
  const [popStyle, setPopStyle] = useState<React.CSSProperties>({});
  const [visible, setVisible] = useState(false);

  const retryTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const rafId = useRef<number>(0);

  const done = () => !!localStorage.getItem(TOUR_KEY);

  // First load
  useEffect(() => {
    if (!done()) setIdx(0);
  }, []);

  const step = idx !== null ? STEPS[idx] : null;

  // Navigate to step's page when step changes
  useEffect(() => {
    if (idx === null || !step || done()) return;
    
    // For exact match on dashboard
    if (step.page === '/' && location.pathname !== '/') {
      navigate('/');
    } 
    // For prefix match on /queues and /workers
    else if (step.page !== '/' && !location.pathname.startsWith(step.page)) {
      navigate(step.page);
    }
  }, [idx]); // eslint-disable-line

  // Position popover on element
  const attach = useCallback((el: HTMLElement) => {
    const rect = el.getBoundingClientRect();
    const PAD = 6;
    setHlStyle({
      position: 'fixed',
      top: rect.top - PAD,
      left: rect.left - PAD,
      width: rect.width + PAD * 2,
      height: rect.height + PAD * 2,
      borderRadius: 8,
      boxShadow: '0 0 0 9999px rgba(0,0,0,0.55), 0 0 0 2px #1d1d1f',
      pointerEvents: 'none',
      zIndex: 9998,
      transition: 'all .2s ease',
    });
    const pos = calcPopoverPos(rect, window.innerWidth, window.innerHeight);
    setPopStyle({
      position: 'fixed',
      top: pos.top,
      left: pos.left,
      width: 340,
      zIndex: 9999,
      transition: 'all .2s ease',
    });
    setVisible(true);
  }, []);

  // Fallback: show centred if element never found
  const showCentred = useCallback(() => {
    setHlStyle({ display: 'none' });
    setPopStyle({
      position: 'fixed',
      top: '50%',
      left: '50%',
      transform: 'translate(-50%, -50%)',
      width: 340,
      zIndex: 9999,
    });
    setVisible(true);
  }, []);

  // Poll DOM every 100ms for up to 3s after step/page changes
  useEffect(() => {
    if (idx === null || !step || done()) { setVisible(false); return; }
    
    const isCorrectPage = step.page === '/' ? location.pathname === '/' : location.pathname.startsWith(step.page);
    if (!isCorrectPage) { setVisible(false); return; }

    if (retryTimer.current) clearInterval(retryTimer.current);
    setVisible(false);
    let attempts = 0;

    retryTimer.current = setInterval(() => {
      const el = document.getElementById(step.elementId);
      if (el) { clearInterval(retryTimer.current!); attach(el); return; }
      if (++attempts > 30) { clearInterval(retryTimer.current!); showCentred(); }
    }, 100);

    return () => { if (retryTimer.current) clearInterval(retryTimer.current); };
  }, [idx, location.pathname, attach, showCentred]); // eslint-disable-line

  // Live-track element position every frame
  useEffect(() => {
    if (!visible || !step) return;
    const loop = () => {
      const el = document.getElementById(step.elementId);
      if (el) attach(el);
      rafId.current = requestAnimationFrame(loop);
    };
    rafId.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafId.current);
  }, [visible, step, attach]);

  const finish = () => {
    localStorage.setItem(TOUR_KEY, 'true');
    setIdx(null);
    setVisible(false);
  };

  const goNext = () => {
    if (idx === null) return;
    if (idx >= STEPS.length - 1) { finish(); return; }
    const s = STEPS[idx];
    if (s.navigateTo) navigate(s.navigateTo);
    setIdx(idx + 1);
  };

  const goPrev = () => {
    if (!idx) return;
    const prev = STEPS[idx - 1];
    if (prev.page !== location.pathname) navigate(prev.page);
    setIdx(idx - 1);
  };

  const skip = () => {
    if (window.confirm('Skip the tour? You can restart by clearing localStorage.')) finish();
  };

  if (!visible || !step || idx === null) return null;

  const isLast = idx === STEPS.length - 1;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Highlight ring */}
      <div style={hlStyle} />

      {/* Popover card */}
      <div style={popStyle}>
        <div style={{
          background: '#ffffff',
          borderRadius: 10,
          boxShadow: '0 12px 40px rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.06)',
          padding: '16px 18px 14px',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}>
          {/* Title row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 7 }}>
            <span style={{ fontWeight: 700, fontSize: 14, color: '#1d1d1f', lineHeight: 1.35, flex: 1 }}>
              {step.title}
            </span>
            <button
              onClick={skip}
              title="Skip tour"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#86868b', fontSize: 20, lineHeight: 1, padding: '0 0 0 10px', flexShrink: 0 }}
            >×</button>
          </div>

          {/* Description */}
          <p style={{ margin: '0 0 14px', fontSize: 13, color: '#3a3a3c', lineHeight: 1.6 }}>
            {step.description}
          </p>

          {/* Footer */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11, color: '#86868b', letterSpacing: 0.2 }}>
              {idx + 1} / {STEPS.length}
            </span>
            <div style={{ display: 'flex', gap: 7 }}>
              {idx > 0 && (
                <button
                  onClick={goPrev}
                  style={{
                    padding: '5px 12px', borderRadius: 6,
                    border: '1px solid #d2d2d7', background: '#f5f5f7',
                    cursor: 'pointer', fontSize: 12.5, color: '#1d1d1f', fontWeight: 500,
                  }}
                >← Back</button>
              )}
              <button
                onClick={goNext}
                style={{
                  padding: '5px 15px', borderRadius: 6,
                  border: 'none',
                  background: '#1d1d1f',   /* black */
                  color: '#ffffff',          /* white */
                  cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
                }}
              >
                {isLast ? 'Done ✓' : 'Next →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

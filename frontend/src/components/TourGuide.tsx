import { useEffect, useRef, useState, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const TOUR_KEY = 'axiom_tour_v4_done';
const ACCENT = '#007aff';

interface Step {
  elementId: string;
  title: string;
  description: string;
  page: string;
  navigateTo?: string;
}

const STEPS: Step[] = [
  {
    page: '/',
    elementId: 'tour-dashboard',
    title: '👋 Welcome to Axiom',
    description: 'Your command center for the distributed job scheduler. The dashboard shows a live overview of all queues, jobs, and workers.',
  },
  {
    page: '/',
    elementId: 'tour-nav-queues',
    title: '📋 Queues',
    description: 'Manage your job queues here — create new ones, configure retry policies, or pause/resume them.',
    navigateTo: '/queues',
  },
  {
    page: '/queues',
    elementId: 'tour-create-queue',
    title: '➕ Create a Queue',
    description: 'Click this to create a new queue. Set its name, max concurrency, and retry strategy (fixed, linear, or exponential backoff with jitter).',
  },
  {
    page: '/',
    elementId: 'tour-nav-workers',
    title: '⚙️ Worker Fleet',
    description: 'Monitor all active worker processes — their hostnames, process IDs, and last heartbeat timestamps.',
    navigateTo: '/workers',
  },
  {
    page: '/workers',
    elementId: 'tour-workers-table',
    title: '🖥 Worker Monitoring',
    description: 'Each row is a live worker process. Workers poll PostgreSQL using FOR UPDATE SKIP LOCKED — no two workers ever claim the same job. Tour complete! 🎉',
  },
];

function getPopoverPos(rect: DOMRect, wW: number, wH: number) {
  const margin = 14;
  const popW = 310;
  const popH = 170;
  let top: number;
  let left: number;

  if (rect.bottom + popH + margin < wH) {
    top = rect.bottom + margin;
  } else if (rect.top - popH - margin > 0) {
    top = rect.top - popH - margin;
  } else {
    top = margin;
  }

  left = rect.left;
  if (left + popW > wW - margin) left = wW - popW - margin;
  if (left < margin) left = margin;

  return { top, left };
}

export default function TourGuide() {
  const location = useLocation();
  const navigate = useNavigate();
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({});
  const [highlightStyle, setHighlightStyle] = useState<React.CSSProperties>({});
  const [visible, setVisible] = useState(false);
  const rafRef = useRef<number>(0);
  const retryRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isDone = () => !!localStorage.getItem(TOUR_KEY);

  // Start on first visit
  useEffect(() => {
    if (!isDone()) setStepIndex(0);
  }, []);

  const step = stepIndex !== null ? STEPS[stepIndex] : null;

  // Navigate to step's page
  useEffect(() => {
    if (stepIndex === null || !step || isDone()) return;
    if (step.page !== location.pathname) navigate(step.page);
  }, [stepIndex]);

  const positionOn = useCallback((el: HTMLElement) => {
    const rect = el.getBoundingClientRect();
    const wW = window.innerWidth;
    const wH = window.innerHeight;
    const pad = 6;

    setHighlightStyle({
      position: 'fixed',
      top: rect.top - pad,
      left: rect.left - pad,
      width: rect.width + pad * 2,
      height: rect.height + pad * 2,
      borderRadius: 8,
      boxShadow: `0 0 0 9999px rgba(0,0,0,0.52), 0 0 0 3px ${ACCENT}`,
      pointerEvents: 'none',
      zIndex: 9998,
      transition: 'top .2s,left .2s,width .2s,height .2s',
    });

    const pos = getPopoverPos(rect, wW, wH);
    setPopoverStyle({
      position: 'fixed',
      top: pos.top,
      left: pos.left,
      width: 310,
      zIndex: 9999,
      transition: 'top .2s,left .2s',
    });
    setVisible(true);
  }, []);

  // Retry finding element for 3s after each step/navigation change
  useEffect(() => {
    if (stepIndex === null || !step || isDone()) { setVisible(false); return; }
    if (step.page !== location.pathname) { setVisible(false); return; }

    if (retryRef.current) clearInterval(retryRef.current);
    setVisible(false);
    let attempts = 0;

    retryRef.current = setInterval(() => {
      const el = document.getElementById(step.elementId);
      if (el) {
        clearInterval(retryRef.current!);
        positionOn(el);
      }
      if (++attempts > 30) clearInterval(retryRef.current!);
    }, 100);

    return () => { if (retryRef.current) clearInterval(retryRef.current); };
  }, [stepIndex, location.pathname, positionOn]);

  // Live-track position
  useEffect(() => {
    if (!visible || !step) return;
    const track = () => {
      const el = document.getElementById(step.elementId);
      if (el) positionOn(el);
      rafRef.current = requestAnimationFrame(track);
    };
    rafRef.current = requestAnimationFrame(track);
    return () => cancelAnimationFrame(rafRef.current);
  }, [visible, step, positionOn]);

  const finish = () => {
    localStorage.setItem(TOUR_KEY, 'true');
    setStepIndex(null);
    setVisible(false);
  };

  const goNext = () => {
    if (stepIndex === null) return;
    if (stepIndex >= STEPS.length - 1) { finish(); return; }
    const s = STEPS[stepIndex];
    if (s.navigateTo) navigate(s.navigateTo);
    setStepIndex(stepIndex + 1);
  };

  const goPrev = () => {
    if (!stepIndex) return;
    const prev = STEPS[stepIndex - 1];
    if (prev.page !== location.pathname) navigate(prev.page);
    setStepIndex(stepIndex - 1);
  };

  const skip = () => {
    if (window.confirm('Skip the tour?')) finish();
  };

  if (!visible || !step || stepIndex === null) return null;

  const isLast = stepIndex === STEPS.length - 1;

  return (
    <>
      <div style={highlightStyle} />
      <div style={popoverStyle}>
        <div style={{
          background: '#fff',
          borderRadius: 10,
          boxShadow: '0 10px 40px rgba(0,0,0,0.18)',
          padding: '16px 18px 13px',
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
            <span style={{ fontWeight: 700, fontSize: 14.5, color: '#1d1d1f', lineHeight: 1.35 }}>
              {step.title}
            </span>
            <button onClick={skip} title="Skip tour" style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#86868b', fontSize: 20, lineHeight: 1, padding: '0 0 0 10px', marginTop: -2,
            }}>×</button>
          </div>

          <p style={{ margin: '0 0 13px', fontSize: 13, color: '#444', lineHeight: 1.55 }}>
            {step.description}
          </p>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 11.5, color: '#86868b' }}>{stepIndex + 1} / {STEPS.length}</span>
            <div style={{ display: 'flex', gap: 6 }}>
              {stepIndex > 0 && (
                <button onClick={goPrev} style={{
                  padding: '4px 11px', borderRadius: 6,
                  border: '1px solid #d2d2d7', background: '#f5f5f7',
                  cursor: 'pointer', fontSize: 12.5, color: '#1d1d1f',
                }}>← Back</button>
              )}
              <button onClick={goNext} style={{
                padding: '4px 14px', borderRadius: 6,
                border: 'none', background: ACCENT, color: '#fff',
                cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
              }}>
                {isLast ? 'Done ✓' : 'Next →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

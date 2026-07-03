import { useEffect, useRef, useState, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const TOUR_KEY = 'axiom_tour_v3_done';

interface Step {
  elementId: string;
  title: string;
  description: string;
  page: string; // pathname this step lives on
  navigateTo?: string; // where to go when Next is clicked from this step
}

const STEPS: Step[] = [
  {
    page: '/',
    elementId: 'tour-dashboard',
    title: '👋 Welcome to Axiom',
    description: 'This is your command center for the distributed job scheduler. The dashboard shows a live overview of all queues, jobs, and workers.',
  },
  {
    page: '/',
    elementId: 'tour-nav-queues',
    title: '📋 Queues',
    description: 'Click here to manage your job queues — create new ones, configure retry policies, pause or resume them.',
    navigateTo: '/queues',
  },
  {
    page: '/queues',
    elementId: 'tour-create-queue',
    title: '➕ Create a Queue',
    description: 'This button opens a form to create a new queue. You can set its name, max concurrency, and retry strategy (fixed, linear, or exponential backoff).',
  },
  {
    page: '/queues',
    elementId: 'tour-pause-btn',
    title: '⏸ Pause a Queue',
    description: 'The Pause button stops workers from picking up new jobs from this queue. Jobs that are currently running finish gracefully — no data is lost.',
  },
  {
    page: '/queues',
    elementId: 'tour-dlq-btn',
    title: '💀 Dead Letter Queue (DLQ)',
    description: 'When a job exceeds its maximum retry attempts, it is automatically routed here. Click this button to inspect and manually requeue dead jobs.',
  },
  {
    page: '/queues',
    elementId: 'tour-queue-link',
    title: '🔍 Explore Queue Jobs',
    description: 'Click on any queue name to open the Job Explorer — see all jobs, their statuses, retry counts, and execution logs.',
  },
  {
    page: '/',
    elementId: 'tour-nav-workers',
    title: '⚙️ Worker Fleet',
    description: 'Navigate here to monitor all active worker processes — their hostnames, process IDs, and last heartbeat timestamps.',
    navigateTo: '/workers',
  },
  {
    page: '/workers',
    elementId: 'tour-workers-table',
    title: '🖥 Worker Monitoring',
    description: 'Each row is a live worker process. Workers poll the database using FOR UPDATE SKIP LOCKED — ensuring no two workers claim the same job. Tour complete! 🎉',
  },
];

function getPopoverPosition(rect: DOMRect, windowW: number, windowH: number) {
  const margin = 12;
  const popW = 320;
  const popH = 160;

  // Try to place below, then above, then right, then left
  if (rect.bottom + popH + margin < windowH) {
    return { top: rect.bottom + margin, left: Math.min(Math.max(rect.left, margin), windowW - popW - margin) };
  }
  if (rect.top - popH - margin > 0) {
    return { top: rect.top - popH - margin, left: Math.min(Math.max(rect.left, margin), windowW - popW - margin) };
  }
  if (rect.right + popW + margin < windowW) {
    return { top: Math.max(rect.top, margin), left: rect.right + margin };
  }
  return { top: Math.max(rect.top, margin), left: Math.max(rect.left - popW - margin, margin) };
}

export default function TourGuide() {
  const location = useLocation();
  const navigate = useNavigate();
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({});
  const [highlightStyle, setHighlightStyle] = useState<React.CSSProperties>({});
  const [visible, setVisible] = useState(false);
  const rafRef = useRef<number>(0);

  // Check if tour was already completed
  const isDone = () => !!localStorage.getItem(TOUR_KEY);

  // Start tour on first visit
  useEffect(() => {
    if (isDone()) return;
    if (location.pathname === '/') {
      setStepIndex(0);
    }
  }, []);

  const currentStep = stepIndex !== null ? STEPS[stepIndex] : null;

  // Navigate to the correct page for this step
  useEffect(() => {
    if (stepIndex === null || isDone()) return;
    const step = STEPS[stepIndex];
    if (step.page !== location.pathname) {
      navigate(step.page);
    }
  }, [stepIndex]);

  // Position the highlight and popover around the target element
  const positionPopover = useCallback(() => {
    if (!currentStep || currentStep.page !== location.pathname) {
      setVisible(false);
      return;
    }
    const el = document.getElementById(currentStep.elementId);
    if (!el) {
      setVisible(false);
      return;
    }

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
      boxShadow: '0 0 0 9999px rgba(0,0,0,0.55)',
      border: '2px solid #6366f1',
      pointerEvents: 'none',
      zIndex: 9998,
      transition: 'all 0.25s ease',
    });

    const pos = getPopoverPosition(rect, wW, wH);
    setPopoverStyle({
      position: 'fixed',
      top: pos.top,
      left: pos.left,
      width: 320,
      zIndex: 9999,
      transition: 'all 0.25s ease',
    });
    setVisible(true);
  }, [currentStep, location.pathname]);

  // Re-position on every animation frame so it tracks dynamic content
  useEffect(() => {
    if (stepIndex === null || isDone()) return;

    let attempts = 0;
    const tryPosition = () => {
      positionPopover();
      attempts++;
      if (!visible && attempts < 40) {
        rafRef.current = requestAnimationFrame(tryPosition);
      }
    };
    rafRef.current = requestAnimationFrame(tryPosition);

    window.addEventListener('resize', positionPopover);
    window.addEventListener('scroll', positionPopover, true);
    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener('resize', positionPopover);
      window.removeEventListener('scroll', positionPopover, true);
    };
  }, [stepIndex, positionPopover, location.pathname]);

  // Retry finding element for up to 3 seconds after navigation
  useEffect(() => {
    if (stepIndex === null || !currentStep || isDone()) return;
    if (currentStep.page !== location.pathname) return;

    let attempts = 0;
    const interval = setInterval(() => {
      const el = document.getElementById(currentStep.elementId);
      if (el) { positionPopover(); clearInterval(interval); }
      if (++attempts > 30) clearInterval(interval);
    }, 100);
    return () => clearInterval(interval);
  }, [stepIndex, location.pathname]);

  const finish = () => {
    localStorage.setItem(TOUR_KEY, 'true');
    setStepIndex(null);
    setVisible(false);
  };

  const handleNext = () => {
    if (stepIndex === null) return;
    const step = STEPS[stepIndex];
    if (stepIndex >= STEPS.length - 1) {
      finish();
      return;
    }
    if (step.navigateTo) {
      navigate(step.navigateTo);
    }
    setStepIndex(stepIndex + 1);
  };

  const handlePrev = () => {
    if (stepIndex === null || stepIndex === 0) return;
    const prevStep = STEPS[stepIndex - 1];
    if (prevStep.page !== location.pathname) {
      navigate(prevStep.page);
    }
    setStepIndex(stepIndex - 1);
  };

  const handleSkip = () => {
    if (confirm('Skip the tour? You can restart it by clearing your browser\'s local storage.')) {
      finish();
    }
  };

  if (stepIndex === null || !visible || !currentStep || isDone()) return null;

  return (
    <>
      {/* Overlay cutout highlight */}
      <div style={highlightStyle} />

      {/* Popover */}
      <div style={popoverStyle}>
        <div style={{
          background: '#fff',
          borderRadius: 10,
          boxShadow: '0 8px 32px rgba(0,0,0,0.22)',
          padding: '18px 20px 14px',
          fontFamily: 'system-ui, sans-serif',
        }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
            <span style={{ fontWeight: 700, fontSize: 15, color: '#111', lineHeight: 1.3 }}>
              {currentStep.title}
            </span>
            <button onClick={handleSkip} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#999', fontSize: 18, lineHeight: 1, padding: '0 0 0 8px' }}>×</button>
          </div>

          {/* Description */}
          <p style={{ margin: '0 0 14px', fontSize: 13.5, color: '#444', lineHeight: 1.5 }}>
            {currentStep.description}
          </p>

          {/* Footer */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 12, color: '#999' }}>{stepIndex + 1} of {STEPS.length}</span>
            <div style={{ display: 'flex', gap: 8 }}>
              {stepIndex > 0 && (
                <button onClick={handlePrev} style={{
                  padding: '5px 12px', borderRadius: 6, border: '1px solid #ddd',
                  background: '#f5f5f5', cursor: 'pointer', fontSize: 13, color: '#555'
                }}>← Prev</button>
              )}
              <button onClick={handleNext} style={{
                padding: '5px 14px', borderRadius: 6, border: 'none',
                background: '#6366f1', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600
              }}>
                {stepIndex >= STEPS.length - 1 ? 'Finish ✓' : 'Next →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

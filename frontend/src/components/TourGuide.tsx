import { useEffect } from 'react';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useLocation, useNavigate } from 'react-router-dom';

const TOUR_COMPLETED_KEY = 'axiom_tour_completed';
let isTourRunning = false;

function waitForElement(selector: string, callback: () => void) {
  if (document.querySelector(selector)) {
    // Add a tiny delay to allow React to paint the element properly
    setTimeout(callback, 100);
    return;
  }
  const observer = new MutationObserver(() => {
    if (document.querySelector(selector)) {
      observer.disconnect();
      setTimeout(callback, 100);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

export default function TourGuide() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    // Only run once and don't overlap instances
    if (isTourRunning || localStorage.getItem(TOUR_COMPLETED_KEY)) return;

    // Only start if we are on the dashboard
    if (location.pathname !== '/') return;

    isTourRunning = true;
    let tour: any;
    
    tour = driver({
      showProgress: true,
      allowClose: false,
      overlayColor: 'rgba(0,0,0,0.5)',
      onDestroyStarted: () => {
        if (!tour.hasNextStep() || confirm('Are you sure you want to skip the tour?')) {
          tour.destroy();
          localStorage.setItem(TOUR_COMPLETED_KEY, 'true');
          isTourRunning = false;
        }
      },
      steps: [
        {
          element: '#tour-dashboard',
          popover: {
            title: 'Welcome to Axiom',
            description: 'This is the main dashboard. Let us take a quick tour of the system. Click Next to continue.',
            side: 'bottom',
            align: 'start'
          }
        },
        {
          element: '#tour-nav-queues',
          popover: {
            title: 'Queue Management',
            description: 'Navigate to the Queues page to configure and manage job queues.',
            side: 'right',
            align: 'center',
            onNextClick: () => {
              navigate('/queues');
              waitForElement('#tour-create-queue', () => tour.moveNext());
            }
          }
        },
        {
          element: '#tour-create-queue',
          popover: {
            title: 'Create Queue',
            description: 'Here you can create a new queue. This creates the underlying structure in PostgreSQL.',
            side: 'bottom',
            align: 'end'
          }
        },
        {
          element: '#tour-queue-link',
          popover: {
            title: 'Job Explorer',
            description: 'Click on a queue name to explore its jobs.',
            side: 'bottom',
            align: 'start',
            onNextClick: () => {
              const link = document.querySelector('#tour-queue-link') as HTMLAnchorElement;
              if (link) {
                navigate(link.getAttribute('href') || '/');
                waitForElement('#tour-submit-success', () => tour.moveNext());
              } else {
                tour.moveNext();
              }
            }
          }
        },
        {
          element: '#tour-submit-success',
          popover: {
            title: 'Submit Immediate Job',
            description: 'This submits a successful job directly to the queue.',
            side: 'bottom',
            align: 'center'
          }
        },
        {
          element: '#tour-submit-failing',
          popover: {
            title: 'Submit Failing Job',
            description: 'This submits a job designed to fail, so you can observe the retry policies in action.',
            side: 'bottom',
            align: 'center'
          }
        },
        {
          element: '#tour-job-row',
          popover: {
            title: 'Job Status & Attempts',
            description: 'Watch the job transition states. Click on any job row to view detailed execution logs.',
            side: 'top',
            align: 'start'
          }
        },
        {
          element: '#tour-nav-queues',
          popover: {
            title: 'Pause Queue',
            description: 'To test pausing, head back to the Queues page.',
            side: 'right',
            align: 'center',
            onNextClick: () => {
              navigate('/queues');
              waitForElement('#tour-pause-btn', () => tour.moveNext());
            }
          }
        },
        {
          element: '#tour-pause-btn',
          popover: {
            title: 'Pause the Queue',
            description: 'Clicking Pause stops workers from picking up new jobs, but allows running ones to finish gracefully.',
            side: 'top',
            align: 'end',
            onNextClick: () => {
              // Go back to Job Explorer to show DLQ button
              const link = document.querySelector('#tour-queue-link') as HTMLAnchorElement;
              if (link) {
                navigate(link.getAttribute('href') || '/');
                waitForElement('#tour-dlq-btn', () => tour.moveNext());
              } else {
                tour.moveNext();
              }
            }
          }
        },
        {
          element: '#tour-dlq-btn',
          popover: {
            title: 'Dead Letter Queue',
            description: 'Jobs that exceed their max retry attempts are routed to the DLQ. Let us go there.',
            side: 'top',
            align: 'end',
            onNextClick: () => {
              const link = document.querySelector('#tour-dlq-btn') as HTMLAnchorElement;
              if (link) {
                navigate(link.getAttribute('href') || '/');
                waitForElement('#tour-dlq-retry', () => tour.moveNext());
              } else {
                tour.moveNext();
              }
            }
          }
        },
        {
          element: '#tour-dlq-retry',
          popover: {
            title: 'Retry Dead Jobs',
            description: 'From the DLQ, you can manually re-queue jobs after fixing the underlying bug.',
            side: 'left',
            align: 'center'
          }
        },
        {
          element: '#tour-nav-workers',
          popover: {
            title: 'Worker Fleet',
            description: 'Finally, monitor your active worker processes here.',
            side: 'right',
            align: 'center',
            onNextClick: () => {
              navigate('/workers');
              waitForElement('#tour-workers-table', () => tour.moveNext());
            }
          }
        },
        {
          element: '#tour-workers-table',
          popover: {
            title: 'Monitoring',
            description: 'View active jobs, heartbeats, and process IDs for your entire stateless fleet. Tour complete!',
            side: 'top',
            align: 'start'
          }
        }
      ]
    });

    // Small delay to ensure DOM is ready
    setTimeout(() => {
      tour.drive();
    }, 500);

    return () => {
      // In development, strict mode might fire useEffect twice. 
      // But we shouldn't necessarily destroy if it's the intended run.
      // We rely on isTourRunning flag to prevent multiple instantiations instead.
    };
  }, [location.pathname, navigate]);

  return null;
}

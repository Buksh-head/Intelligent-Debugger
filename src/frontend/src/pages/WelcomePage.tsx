/**
 * Landing page. Students and instructors sign in or register on their own
 * tab. An account registered on the Instructor tab becomes an instructor
 * automatically. Each account can only use its own tab: a student on the
 * Instructor tab, or an instructor on the Student tab, is signed straight
 * back out with an error.
 */
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';

type Tab = 'student' | 'instructor';
type AuthMode = 'login' | 'register';
const appLogo = '/error-guide-logo.png';

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function WelcomePage() {
  const navigate = useNavigate();
  const { signIn, signUp, signOut } = useAuth();
  const [tab, setTab] = useState<Tab>('student');
  const [mode, setMode] = useState<AuthMode>('login');

  // The email the person signs in with (named userId, but it holds an email).
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Text for the left panel and form heading, based on the selected tab.
  const roleContent = tab === 'student'
    ? {
      eyebrow: 'Error Guide',
      title: 'Learn to debug with confidence.',
      description: 'Work through your own code with staged hints, clear explanations, and small experiments that build lasting debugging skills.',
      features: ['Progressive hints', 'Better feedback'],
      welcome: 'Student Access',
      prompt: mode === 'login' ? 'Sign in to start debugging.' : 'Register to start debugging.',
    }
    : {
      eyebrow: 'Error Guide',
      title: 'See where students get stuck.',
      description: 'Review anonymous cohort patterns, recurring errors, and common misconceptions to support more targeted teaching.',
      features: ['Cohort insights', 'Targeted teaching insights'],
      welcome: 'Instructor Access',
      prompt: mode === 'login' ? 'Sign in to view your cohort dashboard.' : 'Register to view your cohort dashboard.',
    };

  const isRegister = mode === 'register';
  const cardHeight = isRegister ? 'lg:h-[630px]' : 'lg:h-[540px]';

  const resetForm = () => {
    setPassword('');
    setConfirmPassword('');
    setError('');
    setMessage('');
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setMessage('');

    if (!emailPattern.test(userId.trim())) {
      setError('Please enter a valid email address.');
      return;
    }

    // Registration (either tab). The tab decides which role the account gets.
    if (isRegister) {
      if (password.length < 6) {
        setError('Password must be at least 6 characters.');
        return;
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match.');
        return;
      }
      setIsSubmitting(true);
      try {
        const result = await signUp(userId.trim(), password, tab);
        if (result.error) {
          setError(result.error);
          return;
        }
        setMode('login');
        resetForm();
        setMessage('Account created. Confirm your email, then sign in.');
      } catch {
        setError('Unable to create the account. Please try again.');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Instructor sign in
    if (tab === 'instructor') {
      if (!password) {
        setError('Please enter your password.');
        return;
      }
      setIsSubmitting(true);
      try {
        const result = await signIn(userId.trim(), password);
        if (result.error) {
          setError(result.error);
          return;
        }
        if (result.role !== 'instructor') {
          // Not an instructor account: end the session immediately.
          await signOut();
          setError('This account does not have instructor access.');
          return;
        }
        navigate('/instructor');
      } catch {
        setError('Invalid email or password.');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Student sign in
    setIsSubmitting(true);
    try {
      const result = await signIn(userId.trim(), password);
      if (result.error) {
        setError(result.error);
        return;
      }
      if (result.role !== 'student') {
        // Instructor account, or no profile row: end the session immediately.
        await signOut();
        setError(
          result.role === 'instructor'
            ? 'This is an instructor account. Use the Instructor tab.'
            : 'Your account is not set up yet.',
        );
        return;
      }
      navigate('/student/sessions');
    } catch {
      setError('Invalid email or password.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    // The page is one responsive card: the left side explains the app and
    // the right side contains the student or instructor entry form.
    <div className="min-h-screen bg-base-200 px-6 py-10 text-base-content">
      <main className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center justify-center">
        <section className={`grid w-full overflow-hidden rounded-box bg-base-100 shadow-xl lg:grid-cols-[1.05fr_0.95fr] ${cardHeight}`}>
          {/* This panel changes its heading and feature text when the tab changes. */}
          <div className="flex min-h-[540px] flex-col bg-primary px-8 py-12 text-primary-content sm:px-12">
            <div className="mb-6 flex items-center gap-4">
              <img src={appLogo} alt="Error Guide logo" className="h-24 w-24 shrink-0 rounded-box object-contain sm:h-28 sm:w-28" />
              <p className="text-xl font-semibold tracking-wide text-primary-content sm:text-2xl">{roleContent.eyebrow}</p>
            </div>
            <h1 className="max-w-md text-4xl font-bold leading-tight sm:text-5xl">{roleContent.title}</h1>
            <p className="mt-5 max-w-md text-base leading-7 text-primary-content/75">{roleContent.description}</p>
            <div className="mt-auto grid max-w-sm grid-cols-2 gap-8 pb-1 text-sm text-primary-content/75">
              <div className="border-l-2 border-primary-content/70 pl-3">{roleContent.features[0]}</div>
              <div className="border-l-2 border-primary-content/70 pl-3">{roleContent.features[1]}</div>
            </div>
          </div>

          <div className="relative flex flex-col px-8 py-10 sm:px-12">
            {/* The right panel contains the current tab's form controls. */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold">{roleContent.welcome}</h2>
              {roleContent.prompt && <p className="mt-2 text-sm text-base-content/60">{roleContent.prompt}</p>}
            </div>

            {/* Clicking a tab switches the form below. */}
            <div className="mb-7 grid grid-cols-2 rounded-btn bg-base-200 p-1" role="tablist" aria-label="Account type">
              {(['student', 'instructor'] as Tab[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  role="tab"
                  aria-selected={tab === option}
                  className={`rounded-btn px-4 py-2.5 text-sm font-medium capitalize transition ${tab === option ? 'bg-primary text-primary-content shadow-sm' : 'text-base-content/60 hover:text-base-content'}`}
                  onClick={() => {
                    setTab(option);
                    setMode('login');
                    resetForm();
                  }}
                >
                  {option}
                </button>
              ))}
            </div>

            {/* handleSubmit decides whether to sign in or register. */}
            <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-5">
              <label className="form-control w-full gap-2">
                <span className="label-text block pb-2 text-sm font-medium">
                  Email
                </span>
                <input
                  type="email"
                  className="input input-bordered h-12 w-full bg-base-100 text-base-content border-base-300"
                  placeholder={tab === 'instructor' ? 'tutor@university.edu' : 'student@student.uq.edu.au'}
                  autoComplete="username"
                  inputMode="email"
                  maxLength={254}
                  required
                  value={userId}
                  onInvalid={(event) => event.currentTarget.setCustomValidity('Please enter a valid email address.')}
                  onChange={(event) => {
                    event.currentTarget.setCustomValidity('');
                    setUserId(event.target.value);
                  }}
                />
              </label>

              <label className="form-control w-full gap-2">
                <span className="label-text block pb-2 text-sm font-medium">Password</span>
                <input
                  type="password"
                  className="input input-bordered h-12 w-full bg-base-100 text-base-content border-base-300"
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                  placeholder={isRegister ? 'At least 6 characters' : undefined}
                  minLength={6}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </label>

              {isRegister && (
                // Registration adds a second password field to catch typing mistakes.
                <label className="form-control w-full gap-2">
                  <span className="label-text block pb-2 text-sm font-medium">Confirm password</span>
                  <input
                    type="password"
                    className="input input-bordered h-12 w-full border-base-300 bg-base-100 text-base-content"
                    autoComplete="new-password"
                    minLength={6}
                    required
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </label>
              )}

              {/* Only one message is shown at a time: errors take priority over success messages. */}
              {(error || message) && (
                <p className={`relative -top-2 text-sm ${error ? 'text-error' : 'text-success'}`}>
                  {error || message}
                </p>
              )}
              {/* The label changes while a request is being processed. */}
              <div className="mt-auto h-12 w-full lg:absolute lg:bottom-[72px] lg:left-12 lg:right-12 lg:w-auto">
                <button type="submit" className="btn btn-primary h-12 w-full" disabled={isSubmitting}>
                  {isSubmitting
                    ? (isRegister ? 'Creating account...' : 'Signing in...')
                    : isRegister
                      ? (tab === 'student' ? 'Create student account' : 'Create instructor account')
                      : tab === 'student' ? 'Sign in as Student' : 'Sign in as Instructor'}
                </button>
              </div>
            </form>

            <p className="mt-4 min-h-5 text-center text-sm">
              {isRegister ? 'Already have an account?' : 'Need an account?'}{' '}
              <button
                type="button"
                className="link"
                onClick={() => {
                  setMode(mode === 'login' ? 'register' : 'login');
                  resetForm();
                }}
              >
                {isRegister ? 'Sign in' : 'Register'}
              </button>
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
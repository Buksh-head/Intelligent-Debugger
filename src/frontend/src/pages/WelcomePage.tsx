/**
 * Landing page. Students and instructors sign in or register. Students then
 * go to their saved sessions, where they can also delete them.
 */
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';

type Role = 'student' | 'instructor';
type InstructorMode = 'login' | 'register';
const appLogo = '/error-guide-logo.png';

// Default language for each course. The student can still change it.
/**const courseLanguages: Record<string, string> = {
  CSSE1001: 'Python',
  ENGG1001: 'Python',
  SCIE1000: 'Python',
};**/

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function WelcomePage() {
  const navigate = useNavigate();
  const { signIn, signUp } = useAuth();
  const [role, setRole] = useState<Role>('student');
  const [instructorMode, setInstructorMode] = useState<InstructorMode>('login');
  const [studentMode, setStudentMode] = useState<InstructorMode>('login');

  // Instructor email (named userId, but it holds an email). 
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  /**const [course, setCourse] = useState('');
  const [language, setLanguage] = useState('Python');**/
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);


  // The same form supports anonymous student sessions and instructor
  // authentication, so the selected role determines which fields are used.
  // Text for the left panel and form heading, based on the selected tab.
  const roleContent = role === 'student'
    ? {
      eyebrow: 'Error Guide',
      title: 'Learn to debug with confidence.',
      description: 'Work through your own code with staged hints, clear explanations, and small experiments that build lasting debugging skills.',
      features: ['Progressive hints', 'Better feedback'],
      welcome: 'Start a debugging session',
      prompt: studentMode === 'login' ? 'Sign in to start debugging.' : 'Register to start debugging.',
    }
    : {
      eyebrow: 'Error Guide',
      title: 'See where students get stuck.',
      description: 'Review anonymous cohort patterns, recurring errors, and common misconceptions to support more targeted teaching.',
      features: ['Cohort insights', 'Targeted teaching insights'],
      welcome: 'Instructor access',
      prompt: instructorMode === 'login' ? 'Sign in to view your cohort dashboard.' : 'Register to view your cohort dashboard.',
    };

  const authMode = role === 'student' ? studentMode : instructorMode;
  const isRegister = authMode === 'register';
  const cardHeight = isRegister ? 'lg:h-[630px]' : 'lg:h-[540px]';

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setMessage('');

    if (role === 'instructor' && !emailPattern.test(userId.trim())) {
      setError('Please enter a valid instructor email address.');
      return;
    }

    // Instructor sign in
    if (role === 'instructor' && instructorMode === 'login') {
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
        navigate('/instructor');
      } catch {
        setError('Invalid email or password.');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Instructor registration  
    if (role === 'instructor') {
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
        const result = await signUp(userId.trim(), password, 'instructor');
        if (result.error) {
          setError(result.error);
          return;
        }
        setInstructorMode('login');
        setPassword('');
        setConfirmPassword('');
        setMessage('Account created. Confirm your email, then sign in.');
      } catch {
        setError('Unable to create the account. Please try again.');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Student: start a new anonymous session 
    if (studentMode === 'register') {
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
        const result = await signUp(userId.trim(), password, 'student');
        if (result.error) {
          setError(result.error);
          return;
        }
        setStudentMode('login');
        setPassword('');
        setConfirmPassword('');
        setMessage('Account created. Confirm your email, then sign in.');
      } catch {
        setError('Unable to create the account. Please try again.');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Student Sign-in, then start session
    setIsSubmitting(true);
    try {
      const result = await signIn(userId.trim(), password);
      if (result.error) {
        setError(result.error);
        return;
      }
      // Students land on their saved sessions, where they continue one or start a new one.
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
          {/* This panel changes its heading and feature text when the role changes. */}
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
            {/* The right panel contains the current role's form controls. */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold">{roleContent.welcome}</h2>
              {roleContent.prompt && <p className="mt-2 text-sm text-base-content/60">{roleContent.prompt}</p>}
            </div>

            {/* Clicking a tab updates role, which switches the form below. */}
            <div className="mb-7 grid grid-cols-2 rounded-btn bg-base-200 p-1" role="tablist" aria-label="Account type">
              {(['student', 'instructor'] as Role[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  role="tab"
                  aria-selected={role === option}
                  className={`rounded-btn px-4 py-2.5 text-sm font-medium capitalize transition ${role === option ? 'bg-primary text-primary-content shadow-sm' : 'text-base-content/60 hover:text-base-content'}`}
                  onClick={() => {
                    setRole(option);
                    setInstructorMode('login');
                    setStudentMode('login');
                    setPassword('');
                    setConfirmPassword('');
                    setError('');
                    setMessage('');
                  }}
                >
                  {option}
                </button>
              ))}
            </div>

            {/* handleSubmit decides whether to log in, register, or start a student session. */}
            <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-5">
              {/* Students and instructors both sign in with an email and password. */}
              <label className="form-control w-full gap-2">
                <span className="label-text block pb-2 text-sm font-medium">
                  {role === 'instructor' ? 'Instructor email' : 'Email'}
                </span>
                <input
                  type="email"
                  className="input input-bordered h-12 w-full bg-base-100 text-base-content border-base-300"
                  placeholder={role === 'instructor' ? 'tutor@university.edu' : 'student@student.uq.edu.au'}
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
                <span className="label-text block pb-2 text-sm font-medium">{isRegister ? 'Create password' : 'Password'}</span>
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
                      ? (role === 'student' ? 'Create student account' : 'Create instructor account')
                      : role === 'student' ? 'Sign in as student' : 'Continue as instructor'}
                </button>
              </div>
            </form>

            <p className="mt-4 min-h-5 text-center text-sm">
              {isRegister ? 'Already have an account?' : 'Need an account?'}{' '}
              <button
                type="button"
                className="link"
                onClick={() => {
                  if (role === 'student') setStudentMode(studentMode === 'login' ? 'register' : 'login');
                  else setInstructorMode(instructorMode === 'login' ? 'register' : 'login');
                  setPassword('');
                  setConfirmPassword('');
                  setError('');
                  setMessage('');
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

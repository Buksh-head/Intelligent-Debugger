/**
 * Landing page. Students pick a course and language to start an anonymous
 * session. Instructors sign in or register. Students can also delete
 * data from a past session using a saved session ID.
 */
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteStudentData } from '../api';
import { useAuth } from '../auth/useAuth';
import { useStudentSession } from '../session/useStudentSession';

type Role = 'student' | 'instructor';
type InstructorMode = 'login' | 'register';
type PastDeleteStatus = 'idle' | 'deleting' | 'done';
const appLogo = '/error-guide-logo.png';

// Default language for each course. The student can still change it.
const courseLanguages: Record<string, string> = {
  CSSE1001: 'Python',
  ENGG1001: 'Python',
  SCIE1000: 'Python',
};

// Session IDs are UUIDs from crypto.randomUUID(). Checking the shape here
// gives the student a clear message for a mistyped ID instead of a server error.
const sessionIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function WelcomePage() {
  const navigate = useNavigate();
  const { signIn, signUp } = useAuth();
  const { startSession } = useStudentSession();
  const [role, setRole] = useState<Role>('student');
  const [instructorMode, setInstructorMode] = useState<InstructorMode>('login');

  // Instructor email (named userId, but it holds an email). 
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [course, setCourse] = useState('');
  const [language, setLanguage] = useState('Python');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Deleting data from a past session, using an ID the student saved (#23).
  const [showPastDelete, setShowPastDelete] = useState(false);
  const [pastSessionId, setPastSessionId] = useState('');
  const [pastDeleteStatus, setPastDeleteStatus] = useState<PastDeleteStatus>('idle');
  const [pastDeleteError, setPastDeleteError] = useState('');

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
      prompt: 'Choose your course and programming language.',
    }
    : {
      eyebrow: 'Error Guide',
      title: 'See where students get stuck.',
      description: 'Review anonymous cohort patterns, recurring errors, and common misconceptions to support more targeted teaching.',
      features: ['Cohort insights', 'Targeted teaching insights'],
      welcome: 'Instructor access',
      prompt: instructorMode === 'login' ? 'Sign in to view your cohort dashboard.' : 'Register to view your cohort dashboard.',
    };

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
        const result = await signUp(userId.trim(), password);
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
    if (!course) {
      setError('Please select the course you need help with.');
      return;
    }

    startSession({ course, language });
    navigate('/student');
  };

  // Open the "delete past session" popup.
  const openPastDelete = () => {
    setPastSessionId('');
    setPastDeleteStatus('idle');
    setPastDeleteError('');
    setShowPastDelete(true);
  };

  const closePastDelete = () => {
    if (pastDeleteStatus === 'deleting') return;
    setShowPastDelete(false);
  };

  // The backend replies the same way whether or not the session had data,
  // so the success message can't say for certain that something was deleted.
  const handlePastDelete = async () => {
    const id = pastSessionId.trim();
    if (!sessionIdPattern.test(id)) {
      setPastDeleteError("That doesn't look like a session ID. It should look like 3f2a9c1b-7d4e-4b8a-9c6f-1e2d3c4b5a69.");
      return;
    }
    setPastDeleteStatus('deleting');
    setPastDeleteError('');
    try {
      await deleteStudentData(id);
      setPastDeleteStatus('done');
    } catch {
      setPastDeleteError('Could not reach the server. Please try again.');
      setPastDeleteStatus('idle');
    }
  };

  return (
    // The page is one responsive card: the left side explains the app and
    // the right side contains the student or instructor entry form.
    <div className="min-h-screen bg-base-200 px-6 py-10 text-base-content">
      <main className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center justify-center">
        <section className={`grid w-full overflow-hidden rounded-box bg-base-100 shadow-xl lg:grid-cols-[1.05fr_0.95fr] ${role === 'instructor' && instructorMode === 'register' ? 'lg:h-[630px]' : 'lg:h-[540px]'}`}>
          {/* This panel changes its heading and feature text when the role changes. */}
          <div className={`flex flex-col bg-primary px-8 py-12 text-primary-content sm:px-12 ${role === 'instructor' && instructorMode === 'register' ? 'min-h-[630px]' : 'min-h-[540px]'}`}>
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
                    if (option === 'instructor') setInstructorMode('login');
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
              {role === 'instructor' && (
                // Instructors need an email before they can sign in or register.
                <label className="form-control w-full gap-2">
                  <span className="label-text block pb-2 text-sm font-medium">Instructor email</span>
                  <input
                    type="email"
                    className="input input-bordered h-12 w-full bg-base-100 text-base-content border-base-300"
                    placeholder="tutor@university.edu"
                    autoComplete="username"
                    inputMode="email"
                    maxLength={254}
                    required
                    value={userId}
                    onInvalid={(event) => event.currentTarget.setCustomValidity('Please enter a valid instructor email address.')}
                    onChange={(event) => {
                      event.currentTarget.setCustomValidity('');
                      setUserId(event.target.value);
                    }}
                  />
                </label>
              )}

              {role === 'student' ? (
                <>
                  {/* Students choose a course; changing it also selects that course's default language. */}
                  <label className="form-control w-full gap-0">
                    <span className="label-text block pb-2 text-sm font-medium">What course do you need help with?</span>
                    <select
                      className="select select-bordered h-12 w-full bg-base-100 text-base-content"
                      value={course}
                      onChange={(event) => {
                        const selectedCourse = event.target.value;
                        setCourse(selectedCourse);
                        setLanguage(courseLanguages[selectedCourse] ?? 'Python');
                      }}
                    >
                      <option value="" disabled>Select a course</option>
                      <option value="CSSE1001">CSSE1001 Introduction to Software Engineering</option>
                      <option value="CSSE2002" disabled>CSSE2002 Programming in the Large (Coming soon)</option>
                      <option value="ENGG1001">ENGG1001 Introduction to Engineering</option>
                      <option value="DECO1800" disabled>DECO1800 Design Computing (Coming soon)</option>
                      <option value="SCIE1000">SCIE1000 Introduction to Science</option>
                    </select>
                  </label>

                  {/* The language remains editable, although unavailable languages are marked coming soon. */}
                  <label className="form-control w-full gap-0">
                    <span className="label-text block pb-2 text-sm font-medium">Programming language</span>
                    <select
                      className="select select-bordered h-12 w-full bg-base-100 text-base-content"
                      value={language}
                      onChange={(event) => setLanguage(event.target.value)}
                    >
                      <option value="Python">Python</option>
                      <option value="Java" disabled>Java (Coming soon)</option>
                      <option value="JavaScript" disabled>JavaScript (Coming soon)</option>
                    </select>
                  </label>
                </>
              ) : (
                <>
                  {/* Instructor authentication uses a password for both login and registration. */}
                  <label className="form-control w-full gap-2">
                    <span className="label-text block pb-2 text-sm font-medium">{instructorMode === 'register' ? 'Create password' : 'Password'}</span>
                    <input
                      type="password"
                      className="input input-bordered h-12 w-full bg-base-100 text-base-content border-base-300"
                      autoComplete={instructorMode === 'login' ? 'current-password' : 'new-password'}
                      placeholder={instructorMode === 'register' ? 'At least 6 characters' : undefined}
                      minLength={6}
                      required
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                  {instructorMode === 'register' && (
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
                </>
              )}

              {/* Only one message is shown at a time: errors take priority over success messages. */}
              {(error || message) && (
                <p className={`relative -top-2 text-sm ${error ? 'text-error' : 'text-success'}`}>
                  {error || message}
                </p>
              )}
              {/* The label changes while a request is being processed. */}
              <div className="mt-auto h-12 w-full lg:absolute lg:bottom-[72px] lg:left-12 lg:right-12 lg:w-auto">
                <button type="submit" className="btn btn-primary h-12 w-full">
                  {isSubmitting ? (instructorMode === 'login' ? 'Signing in...' : 'Creating account...') : role === 'student' ? 'Continue as student' : instructorMode === 'login' ? 'Continue as instructor' : 'Create instructor account'}
                </button>
              </div>
            </form>
            {/* Instructors can switch between login and registration; students can open data deletion. */}
            {role === 'instructor' ? (
              <p className="mt-4 min-h-5 text-center text-sm">
                {instructorMode === 'login' ? 'Need an account?' : 'Already have an account?'}{' '}
                <button type="button" className="link" onClick={() => { setInstructorMode(instructorMode === 'login' ? 'register' : 'login'); setError(''); setMessage(''); }}>
                  {instructorMode === 'login' ? 'Register' : 'Sign in'}
                </button>
              </p>
            ) : (
              <p className="mt-4 min-h-5 text-center text-sm">
                <button type="button" className="link text-base-content/60 hover:text-base-content" onClick={openPastDelete}>
                  Delete data from a past session
                </button>
              </p>
            )}
          </div>
        </section>
      </main>
      
      {/* This modal is mounted only after the student chooses to delete old session data. */}
      {showPastDelete && (
        <div className="modal modal-open" role="dialog" aria-modal="true" aria-labelledby="past-delete-title">
          <div className="modal-box">
            <h3 id="past-delete-title" className="text-lg font-bold">Delete data from a past session</h3>

            {pastDeleteStatus === 'done' ? (
              <>
                {/* A completed request replaces the input with a confirmation and Close button. */}
                <p className="py-3 text-sm">
                  Done. If any data was stored under that session ID, it has been deleted.
                </p>
                <div className="modal-action">
                  <button type="button" className="btn btn-primary" onClick={closePastDelete}>
                    Close
                  </button>
                </div>
              </>
            ) : (
              <>
                {/* Before completion, the student enters a UUID and can submit or cancel the request. */}
                <p className="py-3 text-sm">
                  Paste the session ID you saved. This deletes the code, errors and hints from that session. It can't be undone.
                </p>
                <input
                  type="text"
                  className="input input-bordered w-full font-mono text-sm"
                  placeholder="e.g. 3f2a9c1b-7d4e-4b8a-9c6f-1e2d3c4b5a69"
                  value={pastSessionId}
                  onChange={(event) => {
                    setPastSessionId(event.target.value);
                    setPastDeleteError('');
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      handlePastDelete();
                    }
                  }}
                  disabled={pastDeleteStatus === 'deleting'}
                  autoFocus
                />
                {pastDeleteError && <p className="mt-2 text-sm text-error">{pastDeleteError}</p>}
                <div className="modal-action">
                  <button type="button" className="btn" onClick={closePastDelete} disabled={pastDeleteStatus === 'deleting'}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn btn-error"
                    onClick={handlePastDelete}
                    disabled={pastDeleteStatus === 'deleting' || !pastSessionId.trim()}
                  >
                    {pastDeleteStatus === 'deleting' ? <span className="loading loading-spinner loading-sm"></span> : 'Delete'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

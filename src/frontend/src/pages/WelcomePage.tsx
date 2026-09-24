import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { ChevronDown } from 'lucide-react';

type Role = 'student' | 'instructor';
type InstructorMode = 'login' | 'register';

const courseLanguages: Record<string, string> = {
  CSSE1001: 'Python',
  CSSE2002: 'Java',
  ENGG1001: 'Python',
  DECO1800: 'JavaScript',
};

type DropdownOption = { value: string; label: string };

function TailwindDropdown({
  value,
  placeholder,
  options,
  onChange,
}: {
  value: string;
  placeholder: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);

  const selectedOption = options.find((option) => option.value === value);

  return (
    <div className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-12 w-full items-center justify-between rounded-full border border-base-content/20 bg-base-100 px-4 text-left text-sm text-base-content hover:border-primary"
      >
        <span className={selectedOption ? '' : 'text-base-content/60'}>
          {selectedOption?.label ?? placeholder}
        </span>
        <ChevronDown size={16} aria-hidden="true" />
      </button>

      {open && (
        <ul className="absolute z-30 mt-2 w-full rounded-2xl border border-base-content/15 bg-base-100 p-1 shadow-xl">
          {options.map((option) => (
            <li key={option.value}>
              <button
                type="button"
                className={`w-full rounded-lg px-3 py-2 text-left hover:bg-base-200 ${
                  option.value === value ? 'active' : ''
                }`}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
              >
                {option.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function WelcomePage() {
  const navigate = useNavigate();
  const { signIn, signUp } = useAuth();
  const [role, setRole] = useState<Role>('student');
  const [instructorMode, setInstructorMode] = useState<InstructorMode>('login');
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [course, setCourse] = useState('');
  const [language, setLanguage] = useState('Python');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const roleContent = role === 'student'
    ? {
        eyebrow: 'Intelligent Debugging Assistant',
        title: 'Learn to debug with confidence.',
        description: 'Work through your own code with staged hints, clear explanations, and small experiments that build lasting debugging skills.',
        features: ['Progressive hints', 'Better feedback'],
        welcome: 'Start a debugging session',
        prompt: 'Choose your course and programming language.',
      }
    : {
        eyebrow: 'Intelligent Debugging Assistant',
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

    if (role === 'instructor' && instructorMode === 'login') {
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
        setMessage('Account created. Check your email if confirmation is required, then sign in.');
      } catch {
        setError('Unable to create the account. Please try again.');
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    if (!course) {
      setError('Please select the course you need help with.');
      return;
    }

    sessionStorage.setItem('debugging-assistant.student-context', JSON.stringify({ course, language }));
    navigate('/student');
  };

  return (
    <div className="min-h-screen bg-base-200 px-6 py-10 text-base-content">
      <main className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center justify-center">
        <section className={`grid w-full overflow-hidden rounded-box bg-base-100 shadow-xl lg:grid-cols-[1.05fr_0.95fr] ${role === 'instructor' && instructorMode === 'register' ? 'lg:h-[630px]' : 'lg:h-[540px]'}`}>
          <div className={`flex flex-col bg-primary px-8 py-12 text-primary-content sm:px-12 ${role === 'instructor' && instructorMode === 'register' ? 'min-h-[630px]' : 'min-h-[540px]'}`}>
            <p className="mb-4 text-sm font-medium uppercase tracking-[0.2em] text-primary-content/65">{roleContent.eyebrow}</p>
            <h1 className="max-w-md text-4xl font-bold leading-tight sm:text-5xl">{roleContent.title}</h1>
            <p className="mt-5 max-w-md text-base leading-7 text-primary-content/75">{roleContent.description}</p>
            <div className="mt-auto grid max-w-sm grid-cols-2 gap-8 pb-1 text-sm text-primary-content/75">
              <div className="border-l-2 border-primary-content/70 pl-3">{roleContent.features[0]}</div>
              <div className="border-l-2 border-primary-content/70 pl-3">{roleContent.features[1]}</div>
            </div>
          </div>

          <div className="relative flex flex-col px-8 py-10 sm:px-12">
            <div className="mb-8">
              <h2 className="text-2xl font-bold">{roleContent.welcome}</h2>
              {roleContent.prompt && <p className="mt-2 text-sm text-base-content/60">{roleContent.prompt}</p>}
            </div>

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

            <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col gap-5">
              {role === 'instructor' && (
                <label className="form-control w-full gap-2">
                  <span className="label-text block pb-2 text-sm font-medium">Instructor email</span>
                  <input
                    type="email"
                    className="input input-bordered h-12 w-full bg-base-100 text-base-content border-base-300"
                    placeholder="tutor@university.edu"
                    autoComplete="username"
                    required
                    value={userId}
                    onChange={(event) => setUserId(event.target.value)}
                  />
                </label>
              )}

              {role === 'student' ? (
                <>
                  <label className="form-control w-full gap-0">
                    <span className="label-text block pb-2 text-sm font-medium">What course do you need help with?</span>
                    <TailwindDropdown
                      value={course}
                      placeholder="Select a course"
                      options={[
                        { value: 'CSSE1001', label: 'CSSE1001 Introduction to Software Engineering' },
                        { value: 'CSSE2002', label: 'CSSE2002 Programming in the Large' },
                        { value: 'ENGG1001', label: 'ENGG1001 Introduction to Engineering' },
                        { value: 'DECO1800', label: 'DECO1800 Design Computing' },
                      ]}
                      onChange={(selectedCourse) => {
                        setCourse(selectedCourse);
                        setLanguage(courseLanguages[selectedCourse] ?? 'Python');
                      }}
                    />
                  </label>

                  <label className="form-control w-full gap-0">
                    <span className="label-text block pb-2 text-sm font-medium">Programming language</span>
                    <TailwindDropdown
                      value={language}
                      placeholder="Select a programming language"
                      options={[
                        { value: 'Python', label: 'Python' },
                        { value: 'Java', label: 'Java' },
                        { value: 'JavaScript', label: 'JavaScript' },
                      ]}
                      onChange={setLanguage}
                    />
                  </label>
                </>
              ) : (
                <>
                  {message && <p className="text-sm text-success">{message}</p>}
                  <label className="form-control w-full gap-2">
                    <span className="label-text block pb-2 text-sm font-medium">{instructorMode === 'register' ? 'Create password' : 'Password'}</span>
                    <input
                      type="password"
                      className="input input-bordered h-12 w-full bg-base-100 text-base-content border-base-300"
                      autoComplete={instructorMode === 'login' ? 'current-password' : 'new-password'}
                      minLength={6}
                      required
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                  </label>
                  {instructorMode === 'register' && (
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

              {error && <p className="text-sm text-error">{error}</p>}
              <div className="mt-auto h-12 w-full lg:absolute lg:bottom-[72px] lg:left-12 lg:right-12 lg:w-auto">
                <button type="submit" className="btn btn-primary h-12 w-full">
                  {isSubmitting ? (instructorMode === 'login' ? 'Signing in...' : 'Creating account...') : role === 'student' ? 'Continue as student' : instructorMode === 'login' ? 'Continue as instructor' : 'Create instructor account'}
                </button>
              </div>
            </form>
            {role === 'instructor' ? (
              <p className="mt-4 min-h-5 text-center text-sm">
                {instructorMode === 'login' ? 'Need an account?' : 'Already have an account?'}{' '}
                <button type="button" className="link" onClick={() => { setInstructorMode(instructorMode === 'login' ? 'register' : 'login'); setError(''); setMessage(''); }}>
                  {instructorMode === 'login' ? 'Register' : 'Sign in'}
                </button>
              </p>
            ) : <div className="mt-4 min-h-5" aria-hidden="true" />}
          </div>
        </section>
      </main>
    </div>
  );
}

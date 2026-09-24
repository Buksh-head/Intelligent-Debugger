import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const courses = ['CSSE1001', 'CSSE2002', 'ENGG1001', 'DECO1800', 'Other'];
const languages = ['Python', 'JavaScript', 'Java', 'C++'];
const courseLanguages: Record<string, string> = {
  CSSE1001: 'Python',
  CSSE2002: 'Java',
  ENGG1001: 'Python',
  DECO1800: 'JavaScript',
};

export default function StudentSetupPage() {
  const navigate = useNavigate();
  const [course, setCourse] = useState('');
  const [language, setLanguage] = useState('');

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    sessionStorage.setItem('debugging-assistant.student-context', JSON.stringify({ course, language }));
    navigate('/');
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-7">
      <section className="card bg-base-200 shadow-sm w-full max-w-lg p-6">
        <div className="mb-6">
          <p className="text-sm text-base-content/60">Student setup</p>
          <h1 className="text-2xl font-semibold mt-1">Set up your debugging session</h1>
          <p className="text-sm mt-2">Tell us which course and coding language you are using.</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">Course</span>
            <select
              className="select select-bordered w-full"
              value={course}
              onChange={(event) => {
                const selectedCourse = event.target.value;
                setCourse(selectedCourse);
                setLanguage(courseLanguages[selectedCourse] ?? '');
              }}
              required
            >
              <option value="" disabled>Select your course</option>
              {courses.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">Coding language</span>
            <select className="select select-bordered w-full" value={language} onChange={(event) => setLanguage(event.target.value)} required>
              <option value="" disabled>Select your coding language</option>
              {languages.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <button type="submit" className="btn btn-primary w-full mt-2">Continue to debugger</button>
        </form>

        <div className="flex justify-between items-center mt-5 text-sm">
          <Link to="/" className="link">Back to student view</Link>
          <Link to="/login" className="link">Instructor login</Link>
        </div>
      </section>
    </main>
  );
}

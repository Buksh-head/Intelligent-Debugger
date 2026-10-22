/**
 * The courses and languages a student can start a session with. Only
 * Python runs in the sandbox for now, so the others are listed as coming soon.
 */

export type CourseOption = {
  code: string;
  name: string;
  language: string; // the course's default language
  available: boolean;
};

export const courses: CourseOption[] = [
  {
    code: "CSSE1001",
    name: "Introduction to Software Engineering",
    language: "Python",
    available: true,
  },
  {
    code: "CSSE2002",
    name: "Programming in the Large",
    language: "Java",
    available: false,
  },
  {
    code: "ENGG1001",
    name: "Introduction to Engineering",
    language: "Python",
    available: true,
  },
  {
    code: "DECO1800",
    name: "Design Computing",
    language: "JavaScript",
    available: false,
  },
  {
    code: "SCIE1000",
    name: "Introduction to Science",
    language: "Python",
    available: true,
  },
];

export const languages = [
  { name: "Python", available: true },
  { name: "Java", available: false },
  { name: "JavaScript", available: false },
];

export const findCourse = (
  code: string | null | undefined,
): CourseOption | undefined => courses.find((course) => course.code === code);

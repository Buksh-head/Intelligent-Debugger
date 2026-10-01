import { useContext } from 'react';
import { StudentSessionContext, type StudentSessionContextValue } from './context';

export function useStudentSession(): StudentSessionContextValue {
  const context = useContext(StudentSessionContext);
  if (!context) {
    throw new Error('useStudentSession must be used within a StudentSessionProvider');
  }
  return context;
}

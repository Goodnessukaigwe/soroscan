import React from 'react';

export const EmptyEventState: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center bg-white border border-dashed border-gray-300 rounded-lg dark:bg-gray-800 dark:border-gray-700">
      <svg
        className="w-12 h-12 text-gray-400 mb-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
        />
      </svg>
      <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">No Events Found</h3>
      <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
        We couldn't find any events matching your query. Try adjusting your search filters or resetting your query.
      </p>
    </div>
  );
};

export default EmptyEventState;

import logging
import time
from contextlib import ExitStack

from django.conf import settings
from django.db import connections
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("django.performance.database")


class SlowQueryLoggerMiddleware(MiddlewareMixin):
    """
    Middleware that monitors and logs database queries exceeding a configurable execution time threshold.
    Uses django.db.connection.execute_wrapper for accurate timing and minimal overhead.
    """

    async def __call__(self, request):
        # Dynamically read threshold, defaulting to 1.0 seconds
        threshold = getattr(settings, "DATABASE_SLOW_QUERY_THRESHOLD", 1.0)
        
        with ExitStack() as stack:
            # We apply the execute_wrapper to all configured databases to support multi-DB setups
            for alias in connections:
                # We need to capture the current alias inside the loop securely.
                def make_wrapper(db_alias):
                    def _execute_wrapper(execute, sql, params, many, context):
                        start_time = time.monotonic()
                        try:
                            return execute(sql, params, many, context)
                        finally:
                            duration = time.monotonic() - start_time
                            if duration > threshold:
                                safe_params = str(params)[:1000] if params else ""
                                try:
                                    logger.warning(
                                        "Slow query detected: SQL [%s] Execution Time: [%.4fs] DB Alias: [%s]",
                                        sql,
                                        duration,
                                        db_alias,
                                        extra={
                                            "duration": round(duration, 4),
                                            "sql": sql,
                                            "params": safe_params,
                                            "db_alias": db_alias,
                                        },
                                    )
                                except Exception:
                                    # Never fail the user request due to logging exceptions
                                    pass
                    return _execute_wrapper
                
                stack.enter_context(connections[alias].execute_wrapper(make_wrapper(alias)))
            
            response = await self.get_response(request)

        return response

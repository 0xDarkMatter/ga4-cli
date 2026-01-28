"""ga4 API client."""

from typing import Optional

import httpx

from .config import get_tokens


class Client:
    """API client for ga4."""

    BASE_URL = "https://analyticsdata.googleapis.com/v1beta"
    TIMEOUT = 30

    def __init__(self):
        tokens = get_tokens()
        self.token = tokens.get("access_token") if tokens else None

    def _headers(self) -> dict:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make GET request."""
        response = httpx.get(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            params=params,
            timeout=self.TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        """Make POST request."""
        response = httpx.post(
            f"{self.BASE_URL}/{endpoint}",
            headers=self._headers(),
            json=data,
            timeout=self.TIMEOUT,
        )
        response.raise_for_status()
        return response.json()




    def list_properties(self, limit: int = 20) -> list:
        """List properties."""
        # TODO: Implement actual API call
        # data = self._get("properties", {"limit": limit})
        # return data.get("properties", [])

        # Placeholder data
        return [
            {"id": "1", "name": "Example Propertie 1"},
            {"id": "2", "name": "Example Propertie 2"},
        ][:limit]

    def get_propertie(self, propertie_id: str) -> Optional[dict]:
        """Get single propertie by ID."""
        # TODO: Implement actual API call
        # try:
        #     data = self._get(f"properties/{propertie_id}")
        #     return data.get("propertie")
        # except httpx.HTTPStatusError as e:
        #     if e.response.status_code == 404:
        #         return None
        #     raise

        # Placeholder data
        if propertie_id in ("1", "2"):
            return {"id": propertie_id, "name": f"Example Propertie {propertie_id}"}
        return None




    def list_reports(self, limit: int = 20) -> list:
        """List reports."""
        # TODO: Implement actual API call
        # data = self._get("reports", {"limit": limit})
        # return data.get("reports", [])

        # Placeholder data
        return [
            {"id": "1", "name": "Example Report 1"},
            {"id": "2", "name": "Example Report 2"},
        ][:limit]

    def get_report(self, report_id: str) -> Optional[dict]:
        """Get single report by ID."""
        # TODO: Implement actual API call
        # try:
        #     data = self._get(f"reports/{report_id}")
        #     return data.get("report")
        # except httpx.HTTPStatusError as e:
        #     if e.response.status_code == 404:
        #         return None
        #     raise

        # Placeholder data
        if report_id in ("1", "2"):
            return {"id": report_id, "name": f"Example Report {report_id}"}
        return None




    def list_dimensions(self, limit: int = 20) -> list:
        """List dimensions."""
        # TODO: Implement actual API call
        # data = self._get("dimensions", {"limit": limit})
        # return data.get("dimensions", [])

        # Placeholder data
        return [
            {"id": "1", "name": "Example Dimension 1"},
            {"id": "2", "name": "Example Dimension 2"},
        ][:limit]

    def get_dimension(self, dimension_id: str) -> Optional[dict]:
        """Get single dimension by ID."""
        # TODO: Implement actual API call
        # try:
        #     data = self._get(f"dimensions/{dimension_id}")
        #     return data.get("dimension")
        # except httpx.HTTPStatusError as e:
        #     if e.response.status_code == 404:
        #         return None
        #     raise

        # Placeholder data
        if dimension_id in ("1", "2"):
            return {"id": dimension_id, "name": f"Example Dimension {dimension_id}"}
        return None




    def list_metrics(self, limit: int = 20) -> list:
        """List metrics."""
        # TODO: Implement actual API call
        # data = self._get("metrics", {"limit": limit})
        # return data.get("metrics", [])

        # Placeholder data
        return [
            {"id": "1", "name": "Example Metric 1"},
            {"id": "2", "name": "Example Metric 2"},
        ][:limit]

    def get_metric(self, metric_id: str) -> Optional[dict]:
        """Get single metric by ID."""
        # TODO: Implement actual API call
        # try:
        #     data = self._get(f"metrics/{metric_id}")
        #     return data.get("metric")
        # except httpx.HTTPStatusError as e:
        #     if e.response.status_code == 404:
        #         return None
        #     raise

        # Placeholder data
        if metric_id in ("1", "2"):
            return {"id": metric_id, "name": f"Example Metric {metric_id}"}
        return None



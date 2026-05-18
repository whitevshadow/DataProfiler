"""
Tests for LCIL Candidate Selector

Tests filtering logic for low-cardinality categorical columns.
"""

import pytest
from profiler.lcil.selector import select_candidates


def test_selector_accepts_low_cardinality_categories():
    """Test that low cardinality categories are selected."""
    profiles = [
        {
            "table_name": "application_paymentmethods",
            "columns": [
                {
                    "column_name": "paymentmethodname",
                    "distinct_count": 4,
                    "cardinality_class": "low",
                    "logical_type": "category",
                    "physical_type": "string",
                    "semantic_type": None,
                    "statistics": {
                        "distinct_count": 4,
                        "top_values": [["Cash", 10], ["Credit Card", 8]],
                    },
                    "sample_values": ["Cash", "Credit Card", "Check"],
                }
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 1
    assert candidates[0].column_name == "paymentmethodname"
    assert candidates[0].distinct_count == 4


def test_selector_accepts_low_cardinality_dimensions():
    """Test that low cardinality dimensions are selected."""
    profiles = [
        {
            "table_name": "application_deliverymethods",
            "columns": [
                {
                    "column_name": "deliverymethodname",
                    "distinct_count": 5,
                    "cardinality_class": "low",
                    "logical_type": "dimension",
                    "physical_type": "string",
                    "semantic_type": None,
                    "statistics": {
                        "distinct_count": 5,
                        "top_values": [["Air", 10], ["Road", 8]],
                    },
                    "sample_values": ["Air", "Road", "Sea"],
                }
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 1
    assert candidates[0].column_name == "deliverymethodname"


def test_selector_accepts_boolean_flags():
    """Test that boolean-like columns are selected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "isactive",
                    "distinct_count": 2,
                    "cardinality_class": "low",
                    "logical_type": "category",
                    "physical_type": "boolean",
                    "semantic_type": "boolean_flag",
                    "statistics": {
                        "distinct_count": 2,
                        "top_values": [["True", 50], ["False", 50]],
                    },
                    "sample_values": [True, False],
                }
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 1
    assert candidates[0].column_name == "isactive"


def test_selector_rejects_medium_cardinality():
    """Test that medium cardinality columns are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "categoryname",
                    "distinct_count": 75,
                    "cardinality_class": "medium",
                    "logical_type": "category",
                    "physical_type": "string",
                    "semantic_type": None,
                    "statistics": {"distinct_count": 75, "top_values": []},
                    "sample_values": [],
                }
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_rejects_high_cardinality():
    """Test that high cardinality columns are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "customername",
                    "distinct_count": 5000,
                    "cardinality_class": "high",
                    "logical_type": "dimension",
                    "physical_type": "string",
                    "semantic_type": None,
                    "statistics": {"distinct_count": 5000, "top_values": []},
                    "sample_values": [],
                }
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_rejects_id_columns():
    """Test that ID columns are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "paymentmethodid",
                    "distinct_count": 4,
                    "cardinality_class": "low",
                    "logical_type": "identifier",
                    "physical_type": "integer",
                    "semantic_type": "identifier",
                    "statistics": {"distinct_count": 4, "top_values": []},
                    "sample_values": [1, 2, 3, 4],
                }
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_rejects_audit_fields():
    """Test that audit fields are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "createdby",
                    "distinct_count": 10,
                    "cardinality_class": "low",
                    "logical_type": "audit",
                    "physical_type": "string",
                    "semantic_type": None,
                    "statistics": {"distinct_count": 10, "top_values": []},
                    "sample_values": ["admin", "user1"],
                },
                {
                    "column_name": "createdat",
                    "distinct_count": 20,
                    "cardinality_class": "low",
                    "logical_type": "timestamp",
                    "physical_type": "datetime",
                    "semantic_type": "timestamp",
                    "statistics": {"distinct_count": 20, "top_values": []},
                    "sample_values": [],
                },
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_rejects_descriptions():
    """Test that description/free text columns are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "description",
                    "distinct_count": 30,
                    "cardinality_class": "low",
                    "logical_type": "description",
                    "physical_type": "string",
                    "semantic_type": "description",
                    "statistics": {"distinct_count": 30, "top_values": []},
                    "sample_values": ["This is a description"],
                }
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_rejects_contact_fields():
    """Test that contact fields are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "email",
                    "distinct_count": 40,
                    "cardinality_class": "low",
                    "logical_type": "contact",
                    "physical_type": "string",
                    "semantic_type": "email",
                    "statistics": {"distinct_count": 40, "top_values": []},
                    "sample_values": ["test@example.com"],
                },
                {
                    "column_name": "phone",
                    "distinct_count": 35,
                    "cardinality_class": "low",
                    "logical_type": "contact",
                    "physical_type": "string",
                    "semantic_type": "phone",
                    "statistics": {"distinct_count": 35, "top_values": []},
                    "sample_values": ["555-1234"],
                },
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_rejects_geospatial_points():
    """Test that raw geospatial coordinates are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "latitude",
                    "distinct_count": 45,
                    "cardinality_class": "low",
                    "logical_type": "geospatial",
                    "physical_type": "float",
                    "semantic_type": "latitude",
                    "statistics": {"distinct_count": 45, "top_values": []},
                    "sample_values": [40.7128],
                },
                {
                    "column_name": "longitude",
                    "distinct_count": 45,
                    "cardinality_class": "low",
                    "logical_type": "geospatial",
                    "physical_type": "float",
                    "semantic_type": "longitude",
                    "statistics": {"distinct_count": 45, "top_values": []},
                    "sample_values": [-74.0060],
                },
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_rejects_urls_and_passwords():
    """Test that URLs and password fields are rejected."""
    profiles = [
        {
            "table_name": "test_table",
            "columns": [
                {
                    "column_name": "website",
                    "distinct_count": 15,
                    "cardinality_class": "low",
                    "logical_type": "category",
                    "physical_type": "string",
                    "semantic_type": "url",
                    "statistics": {"distinct_count": 15, "top_values": []},
                    "sample_values": ["http://example.com"],
                },
                {
                    "column_name": "passwordhash",
                    "distinct_count": 50,
                    "cardinality_class": "low",
                    "logical_type": "category",
                    "physical_type": "string",
                    "semantic_type": None,
                    "statistics": {"distinct_count": 50, "top_values": []},
                    "sample_values": ["abc123"],
                },
            ],
        }
    ]
    
    candidates = select_candidates(profiles, {})
    
    assert len(candidates) == 0


def test_selector_extracts_evidence():
    """Test that evidence is correctly extracted from profile and canonical."""
    profiles = [
        {
            "table_name": "warehouse_packagetypes",
            "columns": [
                {
                    "column_name": "packagetypename",
                    "distinct_count": 8,
                    "cardinality_class": "low",
                    "logical_type": "category",
                    "physical_type": "string",
                    "semantic_type": None,
                    "statistics": {
                        "distinct_count": 8,
                        "top_values": [
                            ["Box", 15],
                            ["Pallet", 12],
                            ["Crate", 10],
                        ],
                    },
                    "sample_values": ["Box", "Pallet", "Crate", "Bag"],
                }
            ],
        }
    ]
    
    canonical_map = {
        "warehouse_packagetypes": {
            "columns": [
                {
                    "name": "packagetypename",
                    "sample_values": ["Box", "Pallet", "Envelope"],
                }
            ]
        }
    }
    
    candidates = select_candidates(profiles, canonical_map)
    
    assert len(candidates) == 1
    candidate = candidates[0]
    
    # Check top_values extracted (could be list or tuple)
    assert len(candidate.top_values) == 3
    first_value = candidate.top_values[0]
    if isinstance(first_value, (list, tuple)):
        assert first_value[0] == "Box" or str(first_value[0]) == "Box"
        assert first_value[1] == 15
    
    # Check sample_values extracted
    assert "Box" in candidate.sample_values
    assert "Pallet" in candidate.sample_values
    
    # Check canonical_samples extracted
    assert "Envelope" in candidate.canonical_samples

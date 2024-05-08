from nmdc_runtime.site.export.ncbi_xml_utils import (
    handle_controlled_identified_term_value,
    handle_controlled_term_value,
    handle_geolocation_value,
    handle_quantity_value,
    handle_text_value,
    handle_timestamp_value,
    handle_float_value,
    handle_string_value,
    load_mappings,
)
import datetime
import xml.etree.ElementTree as ET
import xml.dom.minidom


class NCBISubmissionXML:
    def __init__(
        self, study_id: str, org="National Microbiome Data Collaborative (NMDC)"
    ):
        self.root = ET.Element("Submission")
        self.study_id = study_id
        self.org = org

        # dispatcher dictionary capturing handlers for NMDC object to NCBI flat Attribute
        # type handlers
        self.type_handlers = {
            "QuantityValue": handle_quantity_value,
            "TextValue": handle_text_value,
            "TimestampValue": handle_timestamp_value,
            "ControlledTermValue": handle_controlled_term_value,
            "ControlledIdentifiedTermValue": handle_controlled_identified_term_value,
            "GeolocationValue": handle_geolocation_value,
            "float": handle_float_value,
            "string": handle_string_value,
        }

    def set_element(self, tag, text="", attrib=None, children=None):
        attrib = attrib or {}
        children = children or []
        element = ET.Element(tag, attrib=attrib)
        element.text = text
        for child in children:
            element.append(child)
        return element

    def set_description(
        self, email="aclum@lbl.gov", user="NMDC", first="Alicia", last="Clum", date=None
    ):
        date = date or datetime.datetime.now().strftime("%Y-%m-%d")
        description = self.set_element(
            "Description",
            children=[
                self.set_element("Comment", f"NMDC Submission for {self.study_id}"),
                self.set_element("Submitter", attrib={"user_name": user}),
                self.set_element(
                    "Organization",
                    attrib={"role": "owner", "type": "center"},
                    children=[
                        self.set_element("Name", self.org),
                        self.set_element(
                            "Contact",
                            attrib={"email": email},
                            children=[
                                self.set_element(
                                    "Name",
                                    children=[
                                        self.set_element("First", first),
                                        self.set_element("Last", last),
                                    ],
                                )
                            ],
                        ),
                    ],
                ),
                self.set_element("Hold", attrib={"release_date": date}),
            ],
        )
        self.root.append(description)

    def set_biosample(
        self,
        title,
        spuid,
        sid,
        name,
        pkg,
        nmdc_biosample,
    ):
        attribute_mappings, slot_range_mappings = load_mappings(
            "https://raw.githubusercontent.com/microbiomedata/nmdc-schema/issue-1940/assets/ncbi_mappings/ncbi_attribute_mappings_filled.tsv"
        )

        attributes = {}
        for json_key, value in nmdc_biosample.items():
            if isinstance(value, list):
                continue

            xml_key = attribute_mappings.get(json_key, json_key)
            value_type = slot_range_mappings.get(
                json_key, "string"
            )
            handler = self.type_handlers.get(
                value_type, handle_string_value
            )

            formatted_value = handler(value)
            attributes[xml_key] = formatted_value

        # Create the BioSample XML block with these attributes
        biosample_elements = [
            self.set_element(
                "SampleId",
                children=[
                    self.set_element("SPUID", sid, {"spuid_namespace": self.org})
                ],
            ),
            self.set_element(
                "Descriptor",
                children=[
                    self.set_element("Title", title),
                    self.set_element(
                        "Description", children=[self.set_element("p", spuid)]
                    ),
                ],
            ),
            self.set_element(
                "Organism", children=[self.set_element("OrganismName", name)]
            ),
            self.set_element("Package", pkg),
            self.set_element(
                "Attributes",
                children=[
                    self.set_element(
                        "Attribute", attributes[key], {"attribute_name": key}
                    )
                    for key in sorted(attributes)
                ],
            ),
        ]

        action = self.set_element(
            "Action",
            children=[
                self.set_element(
                    "AddData",
                    attrib={"target_db": "BioSample"},
                    children=[
                        self.set_element(
                            "Data",
                            attrib={"content_type": "XML"},
                            children=[
                                self.set_element(
                                    "XmlContent",
                                    children=[
                                        self.set_element(
                                            "BioSample",
                                            attrib={"schema_version": "2.0"},
                                            children=biosample_elements,
                                        )
                                    ],
                                )
                            ],
                        ),
                        self.set_element(
                            "Identifier",
                            children=[
                                self.set_element(
                                    "SPUID", sid, {"spuid_namespace": self.org}
                                )
                            ],
                        ),
                    ],
                )
            ],
        )
        self.root.append(action)

    def get_submission_xml(self):
        self.set_description()

        # TODO: iterate over all biosamples in the study
        # make call to self.set_biosample() here

        rough_string = ET.tostring(self.root, "unicode")
        reparsed = xml.dom.minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="    ", newl="\n")

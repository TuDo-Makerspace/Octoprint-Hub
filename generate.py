#!/usr/bin/env python3

# Copyright (C) 2024 Patrick Pedersen, TuDo Makerspace

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import configparser
from string import Template

# Read the configuration file
config = configparser.ConfigParser()
config.read("hub.ini")

# Read the HTML template
with open("templates/index_template.html", "r") as file:
    html_template = Template(file.read())

# HTML card template
card_template = Template(
    """
<div class="col-md-4 col-sm-6">
    <div class="card printer-card" data-primary="http://$link" data-fallback="http://$fallback">
        <img src="$image" class="card-img-top printer-image" alt="$name">
        <div class="card-body">
            <h5 class="card-title">$name</h5>
        </div>
    </div>
</div>
"""
)

# Generate the cards from the configuration
cards_html = ""
for section in config.sections():
    name = config[section].get("Name", "Unknown Printer")
    image = config[section].get("Image", "images/default.png")
    link = config[section].get("Link", "#")
    fallback = config[section].get("Fallback", "10.8.0.1")

    card_html = card_template.substitute(
        name=name, image=image, link=link, fallback=fallback
    )
    cards_html += card_html + "\n"

# Generate the final HTML
final_html = html_template.substitute(cards=cards_html)

# Write the HTML to a file
with open("index.html", "w") as f:
    f.write(final_html)

print("index.html generated successfully.")

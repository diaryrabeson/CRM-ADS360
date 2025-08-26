// Script pour charger les pays
async function loadCountries() {
    try {
        const response = await fetch('https://restcountries.com/v3.1/all');
        const countries = await response.json();
        
        const countrySelect = document.getElementById('country');
        countrySelect.innerHTML = '<option value="">Sélectionner un pays</option>';
        
        // Trier les pays par nom
        countries.sort((a, b) => a.name.common.localeCompare(b.name.common));
        
        countries.forEach(country => {
            const option = document.createElement('option');
            option.value = country.cca2; // Code du pays
            option.textContent = country.name.common;
            countrySelect.appendChild(option);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des pays:', error);
    }
}

// Charger les villes basé sur le pays sélectionné
async function loadCities(countryCode) {
    const citySelect = document.getElementById('city');
    citySelect.disabled = true;
    citySelect.innerHTML = '<option value="">Chargement des villes...</option>';
    
    try {
        // Utilisation de l'API Geonames (gratuite avec inscription)
        // Note: Vous devrez obtenir un nom d'utilisateur gratuit sur geonames.org
        const username = 'your_geonames_username'; // À remplacer
        const response = await fetch(`http://api.geonames.org/searchJSON?country=${countryCode}&featureClass=P&maxRows=100&username=${username}`);
        const data = await response.json();
        
        citySelect.innerHTML = '<option value="">Sélectionner une ville</option>';
        
        if (data.geonames && data.geonames.length > 0) {
            data.geonames.forEach(city => {
                const option = document.createElement('option');
                option.value = city.name;
                option.textContent = city.name;
                citySelect.appendChild(option);
            });
            citySelect.disabled = false;
        } else {
            citySelect.innerHTML = '<option value="">Aucune ville trouvée</option>';
        }
    } catch (error) {
        console.error('Erreur lors du chargement des villes:', error);
        citySelect.innerHTML = '<option value="">Erreur de chargement</option>';
    }
}

// Charger les zones/quartiers (plus complexe, souvent besoin d'API payantes)
// Pour l'instant, nous allons simplement permettre la saisie manuelle
function setupZoneSelection() {
    const citySelect = document.getElementById('city');
    const zoneSelect = document.getElementById('zone');
    
    citySelect.addEventListener('change', function() {
        if (this.value) {
            zoneSelect.innerHTML = '<option value="">Saisir manuellement ou sélectionner</option>';
            zoneSelect.disabled = false;
            
            // Option pour saisie manuelle
            const manualOption = document.createElement('option');
            manualOption.value = "manual";
            manualOption.textContent = "↳ Saisir manuellement...";
            zoneSelect.appendChild(manualOption);
        } else {
            zoneSelect.innerHTML = '<option value="">Sélectionner d\'abord une ville</option>';
            zoneSelect.disabled = true;
        }
    });
    
    zoneSelect.addEventListener('change', function() {
        if (this.value === "manual") {
            const manualZone = prompt("Veuillez saisir le nom de la zone/quartier:");
            if (manualZone) {
                // Créer une nouvelle option avec la valeur saisie
                const newOption = document.createElement('option');
                newOption.value = manualZone;
                newOption.textContent = manualZone;
                newOption.selected = true;
                zoneSelect.appendChild(newOption);
                
                // Supprimer l'option de saisie manuelle
                this.remove(this.options[this.selectedIndex]);
            }
        }
    });
}

























/*
    document.addEventListener('DOMContentLoaded', function() {
    // Initialisation des filtres pour chaque onglet
    initFilters();
    
    // Charger les pays au chargement de la page
    loadCountries();
    
    // Configurer les événements pour les sélecteurs de localisation
    document.getElementById('country').addEventListener('change', function() {
        if (this.value) {
            loadCities(this.value);
        } else {
            document.getElementById('city').innerHTML = '<option value="">Sélectionner d\'abord un pays</option>';
            document.getElementById('city').disabled = true;
            document.getElementById('zone').innerHTML = '<option value="">Sélectionner d\'abord une ville</option>';
            document.getElementById('zone').disabled = true;
        }
    });
    
    setupZoneSelection();
    
    // Gestion du changement d'onglet
    const tabEl = document.querySelector('button[data-bs-toggle="tab"]');
    if (tabEl) {
        tabEl.addEventListener('shown.bs.tab', function (event) {
            const target = event.target.getAttribute('data-bs-target');
            console.log('Onglet activé:', target);
            // Réinitialiser les filtres selon l'onglet
            resetFilters(target);
        });
    }
});

// Fonctions pour l'API de localisation
async function loadCountries() {
    try {
        const response = await fetch('https://restcountries.com/v3.1/all');
        const countries = await response.json();
        
        const countrySelect = document.getElementById('country');
        // Sauvegarder l'option par défaut
        const defaultOption = countrySelect.innerHTML;
        countrySelect.innerHTML = defaultOption;
        
        // Trier les pays par nom
        countries.sort((a, b) => a.name.common.localeCompare(b.name.common));
        
        countries.forEach(country => {
            const option = document.createElement('option');
            option.value = country.cca2;
            option.textContent = country.name.common;
            countrySelect.appendChild(option);
        });
    } catch (error) {
        console.error('Erreur lors du chargement des pays:', error);
        // Solution de repli: liste statique des pays principaux
        loadStaticCountries();
    }
}

function loadStaticCountries() {
    const countries = [
        "France", "Belgique", "Suisse", "Canada", "Maroc", "Tunisie", "Algérie",
        "Allemagne", "Espagne", "Italie", "Royaume-Uni", "États-Unis"
    ].sort();
    
    const countrySelect = document.getElementById('country');
    const defaultOption = countrySelect.innerHTML;
    countrySelect.innerHTML = defaultOption;
    
    countries.forEach(country => {
        const option = document.createElement('option');
        option.value = country;
        option.textContent = country;
        countrySelect.appendChild(option);
    });
}

async function loadCities(countryCode) {
    const citySelect = document.getElementById('city');
    citySelect.disabled = true;
    citySelect.innerHTML = '<option value="">Chargement des villes...</option>';
    
    try {
        // Pour une solution réellement gratuite et sans inscription,
        // nous utiliserons une API alternative ou une liste prédéfinie
        const cities = await getCitiesByCountry(countryCode);
        
        citySelect.innerHTML = '<option value="">Sélectionner une ville</option>';
        
        if (cities.length > 0) {
            cities.forEach(city => {
                const option = document.createElement('option');
                option.value = city;
                option.textContent = city;
                citySelect.appendChild(option);
            });
            citySelect.disabled = false;
        } else {
            // Activer la saisie manuelle si aucune ville n'est trouvée
            citySelect.innerHTML = '<option value="">Aucune ville trouvée - Saisir manuellement</option>';
            citySelect.disabled = false;
        }
    } catch (error) {
        console.error('Erreur lors du chargement des villes:', error);
        citySelect.innerHTML = '<option value="">Erreur de chargement - Saisir manuellement</option>';
        citySelect.disabled = false;
    }
}

// Cette fonction retourne des villes basées sur le pays (données statiques)
async function getCitiesByCountry(countryCode) {
    // Mapping de code de pays vers des villes (simplifié)
    const countryCities = {
        "FR": ["Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Strasbourg", "Montpellier", "Bordeaux", "Lille"],
        "BE": ["Bruxelles", "Anvers", "Gand", "Charleroi", "Liège", "Bruges", "Namur", "Louvain", "Mons", "Malines"],
        "CH": ["Zurich", "Genève", "Bâle", "Lausanne", "Berne", "Winterthour", "Lucerne", "Saint-Gall", "Lugano", "Bienne"],
        // Ajouter d'autres pays selon les besoins
    };
    
    // Retourner les villes pour le pays ou une liste vide
    return countryCities[countryCode] || [];
}

function setupZoneSelection() {
    const citySelect = document.getElementById('city');
    const zoneSelect = document.getElementById('zone');
    
    citySelect.addEventListener('change', function() {
        if (this.value) {
            zoneSelect.innerHTML = '<option value="">Sélectionner une zone</option>';
            
            // Option pour saisie manuelle
            const manualOption = document.createElement('option');
            manualOption.value = "manual";
            manualOption.textContent = "Saisir manuellement...";
            zoneSelect.appendChild(manualOption);
            
            zoneSelect.disabled = false;
        } else {
            zoneSelect.innerHTML = '<option value="">Sélectionner d\'abord une ville</option>';
            zoneSelect.disabled = true;
        }
    });
    
    zoneSelect.addEventListener('change', function() {
        if (this.value === "manual") {
            const manualZone = prompt("Veuillez saisir le nom de la zone/quartier:");
            if (manualZone) {
                // Créer une nouvelle option avec la valeur saisie
                const newOption = document.createElement('option');
                newOption.value = manualZone;
                newOption.textContent = manualZone;
                newOption.selected = true;
                
                // Ajouter avant l'option de saisie manuelle
                zoneSelect.insertBefore(newOption, zoneSelect.lastChild);
            } else {
                this.selectedIndex = 0;
            }
        }
    });
}*/
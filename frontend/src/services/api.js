import axios from "axios";

const API_BASE = "http://localhost:8000/api";

export const uploadPDF = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const res = await axios.post(`${API_BASE}/upload`, formData);
  return res.data;
};

export const runAnalysis = async (analysisId) => {
  const res = await axios.post(`${API_BASE}/analyze/${analysisId}`);
  return res.data;
};

export const getAnalysis = async (analysisId) => {
  const res = await axios.get(`${API_BASE}/analysis/${analysisId}`);
  return res.data;
};
